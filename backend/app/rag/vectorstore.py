"""Local Chroma vector store wrapper.

We always supply explicit embeddings computed by the hosted embedder and never
use Chroma's built-in default embedding function, which would download and run
a *local* model — forbidden here. A defensive embedding function is installed
so any accidental call fails loudly instead of fetching model weights.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .chunking import Chunk
from .embeddings import Embedder


class _NoLocalEmbeddingFunction:
    """Guards against accidental use of a local embedding model."""

    def __call__(self, input: Any) -> Any:
        raise RuntimeError(
            "Local embedding models are disabled. Embeddings must be supplied "
            "explicitly by the configured hosted embedder."
        )

    def name(self) -> str:  # type: ignore[empty-body]
        return "no-local-embeddings"


class VectorStore:
    def __init__(self, path: Path, embedder: Embedder, corpus_identity: str = "") -> None:
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        identity = getattr(embedder, "index_identity", type(embedder).__name__)
        self.collection_name = "policy_" + hashlib.sha256((identity + "|" + corpus_identity).encode()).hexdigest()[:16]
        import os

        # Disable Chroma's product telemetry (it would otherwise fail noisily
        # against newer posthog versions and phone home).
        os.environ["ANONYMIZED_TELEMETRY"] = "False"
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=_NoLocalEmbeddingFunction(),
        )

    def reset(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=_NoLocalEmbeddingFunction(),
        )

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        # Embed and store the section heading together with the body so queries
        # can match headings, and citations remain self-contained.
        documents = [f"{c.section}\n{c.text}" for c in chunks]
        embeddings = self.embedder.embed_texts(documents)
        self._collection.add(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=documents,
            metadatas=[{"section": c.section, "id": c.id} for c in chunks],
        )

    def query(self, text: str, top_k: int = 4) -> list[dict[str, Any]]:
        if not self.count():
            return []
        q_emb = self.embedder.embed_texts([text])
        res = self._collection.query(
            query_embeddings=q_emb,
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        ids = res["ids"][0]
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]
        out: list[dict[str, Any]] = []
        for i, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append(
                {
                    "id": meta.get("id", i),
                    "section": meta.get("section", i),
                    "text": doc,
                    "score": round(max(0.0, 1.0 - dist), 4),
                }
            )
        return out

    def count(self) -> int:
        return self._collection.count()

    @property
    def fingerprint(self) -> str | None:
        p = self.path / (self.collection_name + ".fingerprint")
        return p.read_text() if p.exists() else None

    def set_fingerprint(self, value: str) -> None:
        (self.path / (self.collection_name + ".fingerprint")).write_text(value)
