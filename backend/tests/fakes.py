"""Deterministic test doubles for the hosted LLM and embedding providers.

Production uses hosted inference exclusively (Gemini / OpenAI / Anthropic).
These fakes exist only so the workflow, routing, and persistence tests run
offline and deterministically. They are intentionally small scripted
substitutes and are never imported by the application.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any

_CLAIM_ID_RE = re.compile(r"\bCLM-[\w-]{3,}\b", re.I)
_POLICY_RE = re.compile(r"\bPOL-[\w-]{2,}\b", re.I)
_DOLLAR_RE = re.compile(r"\$\s?([\d][\d,]*(?:\.\d+)?)")

_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do",
    "does", "did", "have", "has", "had", "of", "to", "in", "on", "at", "for",
    "with", "by", "from", "up", "down", "out", "about", "and", "or", "but",
    "if", "so", "as", "it", "its", "this", "that", "these", "those", "my",
    "your", "our", "their", "i", "you", "we", "they", "me", "us", "them",
    "he", "she", "him", "her", "what", "which", "who", "when", "where", "how",
    "why", "can", "could", "will", "would", "should", "shall", "may", "might",
    "get", "got", "cover", "covers", "covered", "coverage", "policy", "claim",
    "claims", "please", "tell", "know", "any", "there", "here", "not", "no",
    "yes", "very", "really", "just", "also", "damage", "damages", "damaged",
    "incident", "happen", "happened", "need", "want", "like", "help", "does",
}

_SUFFIXES = ("ing", "ed", "es", "s")


def _stem(tok: str) -> str:
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)]
    return tok


class FakeEmbedder:
    """Naive token-overlap embedder for offline retrieval tests (test double)."""

    _DIM = 256

    def dim(self) -> int:
        return self._DIM

    def _tokens(self, text: str) -> list[str]:
        out = []
        for t in re.findall(r"[a-z0-9]+", text.lower()):
            t = _stem(t)
            if t not in _STOP:
                out.append(t)
        return out

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self._DIM
        for tok in self._tokens(text):
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "big")
            vec[h % self._DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeLanguageModel:
    """Scripted language-model substitute for offline workflow tests.

    Verdicts are derived from the retrieved passages as verbatim quotes using
    simple rules for the sample policy. This is a test double — the hosted
    model does the real reasoning.
    """

    def review_evidence(self, question, sources, history, analysis):
        from types import SimpleNamespace
        return SimpleNamespace(sufficient=True, search_queries=[])

    def compose_clarification(self, question, missing_fact, sources, history, policy_terms=None, clarification_plan=None, claim_requested=False):
        return missing_fact

    def compose_claim_offer(self, message, history):
        return "Would you like to start a claim?"

    def rewrite_query(self, question, history):
        previous = next((h['content'] for h in reversed(history) if h['role'] == 'user'), '')
        return previous + ' ' + question if previous else question

    def resolve_claim_id(self, message, history):
        return self.extract_claim_id(message)

    def select_claims(self, query, candidates):
        return [c['claim_id'] for c in candidates]

    def classify_intent(self, message: str, history: list[dict[str, str]]) -> tuple[str, str]:
        m = message.lower()
        if _CLAIM_ID_RE.search(message):
            intent = "claim_status"
        elif any(k in m for k in ("file a claim", "file claim", "submit a claim", "new claim",
                                  "make a claim", "report a claim", "i want to claim", "start a claim")):
            intent = "claim_submit"
        elif any(k in m for k in ("claim status", "track", "check my claim", "where is my claim",
                                  "status of", "my claim", "my claims", "happened to my")):
            intent = "claim_status"
        elif _POLICY_RE.search(message) and _DOLLAR_RE.search(message):
            intent = "claim_submit"
        elif any(k in m for k in ("hi", "hello", "hey", "thanks", "thank you")) and len(m.split()) <= 4:
            intent = "chitchat"
        else:
            intent = "coverage"
        return intent, self.rewrite_query(message, history)

    def extract_claim_id(self, message: str) -> str | None:
        m = _CLAIM_ID_RE.search(message)
        return m.group(0).upper() if m else None

    def extract_claim_fields(self, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        pm = _POLICY_RE.search(message)
        if pm:
            out["policy_number"] = pm.group(0).upper()
        dm = _DOLLAR_RE.search(message)
        if dm:
            out["amount"] = float(dm.group(1).replace(",", ""))
        m = message.lower()
        if any(k in m for k in ("water", "pipe", "burst", "leak", "flood", "plumbing")):
            out["claim_type"] = "Water Damage"
        elif any(k in m for k in ("laptop", "tv", "ring", "jewelry", "furniture", "electronics",
                                  "personal property", "phone", "computer", "camera", "watch")):
            out["claim_type"] = "Personal Property"
        # A description is only an incident description when the message also
        # names a cause/category; a bare "policy POL-… and $X damage" fill-in
        # must not overwrite the description collected from an earlier turn.
        if "claim_type" in out and len(message.split()) >= 5:
            out["description"] = message.strip()
        return out

    def analyze_policy(self, question, sources, history):
        context = next((h["content"] for h in reversed(history) if h["content"].startswith("Existing draft description")), "")
        q = (context + " " + question).lower()
        empty = {"verdict": "unsupported", "facts": [], "cited_ids": [], "clarification": ""}
        if not sources:
            return empty
        # Resolve follow-up references ("that", "deductible", …) against the
        # most recent user turn.
        if re.search(r"\b(it|that|those|deductible|how much|what limit)\b", q, re.I):
            previous = next(
                (h.get("content", "") for h in reversed(history or []) if h.get("role") == "user"),
                "",
            )
            if previous:
                q = f"{previous}\n{q}"
        text_by_id = {s["id"]: s["text"] for s in sources}
        sentences = {
            sid: [t.strip() for t in re.split(r"(?<=[.!?])\s+|\n", txt)
                  if t.strip() and t.strip() not in {s.get('section') for s in sources} and not re.match(r"^section\s+\d+\s*[—-]", t.strip(), re.I)]
            for sid, txt in text_by_id.items()
        }
        # Exclusions (flood / gradual leak) take precedence over property category.
        for sid, parts in sentences.items():
            for part in parts:
                if "excluded" in part.lower() and (
                    ("flood" in q and "flood" in part.lower())
                    or (any(w in q for w in ("leak", "slow", "gradual", "seep", "drip"))
                        and "gradual" in part.lower()
                        and not any(w in q for w in ("burst", "sudden", "broke")))
                ):
                    return {"verdict": "excluded", "facts": [part], "cited_ids": [sid],
                            "clarification": ""}
        # Personal property: appraisal threshold.
        value = None
        vm = _DOLLAR_RE.search(q)
        if vm:
            value = float(vm.group(1).replace(",", ""))
        personal = any(k in q for k in ("laptop", "tv", "ring", "jewelry", "furniture",
                                        "electronics", "personal property", "phone", "computer",
                                        "camera", "watch", "item"))
        if personal:
            for sid, parts in sentences.items():
                for part in parts:
                    if "electronics" in part.lower() or "appraisal" in part.lower():
                        if value is not None and value > 2500:
                            return {"verdict": "conditional", "facts": [part], "cited_ids": [sid],
                                    "clarification": "Do you have an appraisal receipt?"}
                        if value is not None:
                            return {"verdict": "covered", "facts": [part], "cited_ids": [sid],
                                    "clarification": ""}
                        return {"verdict": "uncertain", "facts": [part], "cited_ids": [sid],
                                "clarification": "What caused the damage and what is its value?"}
        # Water damage.
        water = any(k in q for k in ("water", "pipe", "plumbing", "flood", "leak"))
        if water:
            for sid, parts in sentences.items():
                for part in parts:
                    if "burst" in part.lower() or "water damage" in part.lower():
                        if any(w in q for w in ("burst", "sudden", "broke", "ruptured")):
                            return {"verdict": "covered", "facts": [part], "cited_ids": [sid],
                                    "clarification": ""}
                        return {"verdict": "uncertain", "facts": [part], "cited_ids": [sid],
                                "clarification": "What caused the water damage: a sudden pipe burst, "
                                                 "a gradual leak, or flooding?"}
        return empty

    def compose_answer(self, question, verdict, facts, sections, history=None):
        labels = {"covered": "Covered", "excluded": "Excluded",
                  "conditional": "Conditional coverage", "uncertain": "More information needed",
                  "unsupported": "Coverage not established"}
        return labels.get(verdict, verdict) + ". " + " ".join(facts)
