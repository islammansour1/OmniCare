"""RAG pipeline: ingest the policy once, retrieve on demand."""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..config import settings
from ..observability import log_event
from .chunking import Chunk, load_and_chunk, CHUNKER_VERSION
from .embeddings import Embedder, get_embedder
from .vectorstore import VectorStore

class RagPipeline:
    def __init__(
        self,
        embedder: Embedder | None = None,
        chroma_dir=None,
        policy_file=None,
    ) -> None:
        self._embedder = embedder
        self.chroma_dir = chroma_dir or settings.chroma_dir
        self.policy_file = Path(policy_file) if policy_file else settings.policy_file
        self._store: VectorStore | None = None
        self._chunks: list[Chunk] | None = None

    @property
    def embedder(self) -> Embedder:
        # Resolve lazily so importing the package never requires credentials;
        # fail-fast happens on first use (startup ingest / first retrieve).
        if self._embedder is None:
            self._embedder = get_embedder()
        return self._embedder

    @property
    def store(self) -> VectorStore:
        if self._store is None:
            self._store = VectorStore(self.chroma_dir, self.embedder)
        return self._store

    def ingest(self, force: bool = False) -> int:
        """Chunk + embed + store the policy. Idempotent: force rebuilds."""
        chunks = load_and_chunk(self.policy_file)
        if not chunks:
            raise RuntimeError(f"no policy sections found in {self.policy_file}")
        fingerprint = hashlib.sha256((CHUNKER_VERSION + self.policy_file.read_text()).encode()).hexdigest()
        # Versioned collections keep the last working corpus intact if re-embedding fails.
        store = VectorStore(self.chroma_dir, self.embedder, corpus_identity=fingerprint)
        if force or store.count() != len(chunks) or store.fingerprint != fingerprint:
            if store.count():
                store.reset()
            store.add_chunks(chunks)
            store.set_fingerprint(fingerprint)
            log_event("rag.ingested", chunks=len(chunks), mode=self.embedder.__class__.__name__)
        self._store, self._chunks = store, chunks
        return len(chunks)

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        if self._chunks is None:
            self.ingest()
        top_k = settings.rag_top_k if top_k is None else top_k
        if top_k < 1:
            raise ValueError("top_k must be positive")
        results = self.store.query(query, top_k=top_k)
        sources: list[dict] = []
        for r in results:
            if r["score"] < settings.rag_score_threshold:
                continue
            sources.append(
                {
                    "id": r["id"],
                    "section": r["section"],
                    "text": r["text"],
                    "score": r["score"],
                }
            )
        if settings.rag_hybrid_search:
            # BM25 over the local policy sections + semantic rank fusion.
            # Keep numeric amounts and exact policy terminology searchable.
            def tokens(text):
                return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
            chunks = self.get_chunks()
            docs = [tokens(c.section + " " + c.text) for c in chunks]
            terms = set(tokens(query))
            avg_len = sum(map(len, docs)) / max(len(docs), 1) or 1
            lexical = []
            for chunk, doc in zip(chunks, docs):
                counts = Counter(doc)
                score = 0.0
                for term in terms:
                    df = sum(term in d for d in docs)
                    freq = counts[term]
                    if freq:
                        idf = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
                        score += idf * freq * 2.2 / (freq + 1.2 * (0.25 + 0.75 * len(doc) / avg_len))
                if score:
                    lexical.append((score, {"id": chunk.id, "section": chunk.section,
                                           "text": chunk.section + "\n" + chunk.text, "score": 0.0}))
            lexical.sort(key=lambda pair: -pair[0])
            ranks, documents = {}, {}
            for ranking in (sources, [item for _, item in lexical]):
                for rank, item in enumerate(ranking, 1):
                    ranks[item['id']] = ranks.get(item['id'], 0) + 1 / (60 + rank)
                    documents[item['id']] = item
            sources = [{**documents[sid], 'score': ranks[sid]} for sid in
                       sorted(ranks, key=lambda sid: -ranks[sid])[:top_k]]
        log_event(
            "rag.retrieved",
            query=query[:60],
            source_ids=[s["id"] for s in sources],
            scores=[s["score"] for s in sources],
        )
        return sources

    def get_chunks(self) -> list[Chunk]:
        return list(self._chunks) if self._chunks is not None else load_and_chunk(self.policy_file)


# Singleton (tests may construct isolated instances).
pipeline = RagPipeline()
