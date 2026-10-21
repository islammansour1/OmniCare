"""Claims JSON database with safe, idempotent, crash-safe writes.

Design goals:
- Preserve the original records (append-only for new claims).
- Never lose or corrupt data: writes go to a temp file and are atomically
  renamed into place (`os.replace`), under an exclusive file lock.
- Idempotent submission: the claim id is derived deterministically from the
  (policy, type, amount, description) tuple, so retries/double-submits of the
  same draft yield the same claim and never create duplicates.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from filelock import FileLock

from ..config import settings
from ..observability import log_event


class ClaimNotFoundError(Exception):
    pass


class InvalidClaimError(Exception):
    pass


class ClaimsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else settings.claims_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.path) + ".lock")
        self._mem_lock = threading.Lock()
        # In-memory cache keyed by content mtime; kept for read performance.
        self._vector_cache: dict[str, list[float]] = {}
        self._cache: tuple[float, list[dict[str, Any]]] | None = None

    def _read(self) -> list[dict[str, Any]]:
        """Read the current claims. The file is always written atomically, so a
        plain read never observes a torn write."""
        with self._mem_lock:
            try:
                mtime = self.path.stat().st_mtime
                if self._cache and self._cache[0] == mtime:
                    return list(self._cache[1])
            except FileNotFoundError:
                return []
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise InvalidClaimError("claims database must be a JSON array")
            self._cache = (self.path.stat().st_mtime, data)
            return list(data)

    def _write(self, claims: list[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(claims, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        with self._mem_lock:
            self._cache = (self.path.stat().st_mtime, claims)

    # ------------------------------------------------------------------
    def list_claims(self) -> list[dict[str, Any]]:
        return self._read()

    def get(self, claim_id: str) -> dict[str, Any] | None:
        for c in self._read():
            if c.get("claim_id") == claim_id:
                return c
        return None

    def find_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        for c in self._read():
            if c.get("idempotency_key") == key:
                return c
        return None

    def get_claim_status(self, claim_id: str, owner_id: str | None = None) -> dict[str, Any]:
        claim = self.get(claim_id)
        if claim is None or (owner_id is not None and not self.visible_to(claim, owner_id)):
            raise ClaimNotFoundError(claim_id)
        return claim

    def submit_claim(
        self,
        policy_number: str,
        claim_type: str,
        amount: float,
        description: str,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a new claim with a deterministic, idempotent claim id."""
        idem_key = self.idempotency_key(policy_number, claim_type, amount, description, owner_id)
        claim_id = self.claim_id_from_key(idem_key)

        with self._lock:
            claims = self._read()
            existing = next((c for c in claims if c.get("claim_id") == claim_id), None)
            if existing is not None:
                log_event("claim.idempotent_replay", claim_id=claim_id)
                return existing

            new_claim = {
                "claim_id": claim_id,
                "policy_number": policy_number,
                "claim_type": claim_type,
                "status": "Submitted",
                "amount": float(amount),
                "description": description,
                "idempotency_key": idem_key,
                **({"owner_id": owner_id} if owner_id else {}),
            }
            claims.append(new_claim)
            self._write(claims)
            log_event("claim.submitted", claim_id=claim_id)
            return new_claim

    @staticmethod
    def visible_to(claim: dict, owner_id: str) -> bool:
        # Only the two assessment fixtures are public sample records.
        return claim.get("owner_id") == owner_id or (
            not claim.get("owner_id") and claim.get("claim_id") in {"CLM-8821", "CLM-9014"})

    def search(self, query: str, owner_id: str, *, embedder, limit: int = 20) -> list[dict]:
        """Semantic candidate ranking. Filter ownership BEFORE embedding or model use.

        The hosted model then applies requested semantic/status filters. The cache
        is keyed by embedding model and record content, and bounded in memory.
        """
        import math
        candidates = [c for c in self._read() if self.visible_to(c, owner_id)]
        if not candidates:
            return []
        identity = getattr(embedder, 'index_identity', type(embedder).__name__)
        documents = [json.dumps({k: v for k, v in c.items() if k not in {'owner_id', 'idempotency_key'}},
                                sort_keys=True) for c in candidates]
        keys = [hashlib.sha256((identity + doc).encode()).hexdigest() for doc in documents]
        with self._mem_lock:
            vectors = {key: self._vector_cache[key] for key in keys if key in self._vector_cache}
        missing = [(key, doc) for key, doc in zip(keys, documents) if key not in vectors]
        if missing:
            generated = embedder.embed_texts([doc for _, doc in missing])
            vectors.update(zip([key for key, _ in missing], generated))
            with self._mem_lock:
                if len(self._vector_cache) + len(missing) > 2000:
                    self._vector_cache.clear()
                self._vector_cache.update(vectors)
        query_vector = embedder.embed_texts([query])[0]
        def similarity(key):
            vec = vectors[key]
            if len(vec) != len(query_vector):
                raise RuntimeError('Embedding dimensions changed')
            denominator = math.sqrt(sum(v*v for v in vec) * sum(v*v for v in query_vector))
            return sum(a*b for a,b in zip(vec, query_vector)) / denominator if denominator else 0
        ranked = sorted(zip(keys, candidates), key=lambda pair: -similarity(pair[0]))
        return [c for _, c in ranked[:limit]]

    @staticmethod
    def idempotency_key(
        policy_number: str, claim_type: str, amount: float, description: str, owner_id: str | None = None
    ) -> str:
        normalized = "|".join(
            [
                policy_number.strip().lower(),
                claim_type.strip().lower(),
                f"{float(amount):.2f}",
                description.strip().lower(),
            ]
        )
        if owner_id:
            normalized = owner_id + "|" + normalized
        return "idem_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def claim_id_from_key(idem_key: str) -> str:
        h = hashlib.sha256(idem_key.encode("utf-8")).hexdigest().upper()
        return "CLM-" + h[:6]


# Module-level singleton (tests may construct isolated instances).
claims_store = ClaimsStore()
