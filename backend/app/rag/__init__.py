"""RAG: section-aware chunking, hosted embeddings, local Chroma."""
from .pipeline import RagPipeline, pipeline
from .chunking import chunk_policy
from .embeddings import Embedder, OpenAIEmbedder, get_embedder

__all__ = [
    "RagPipeline",
    "pipeline",
    "chunk_policy",
    "Embedder",
    "OpenAIEmbedder",
    "get_embedder",
]
