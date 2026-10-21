"""Provider resolution summary for observability and /health."""
from __future__ import annotations

from .config import settings


def provider_summary() -> dict[str, str]:
    return {
        "llm": settings.llm_provider_resolved if settings.has_llm else "unavailable",
        "embeddings": settings.embedding_provider_resolved if settings.has_embeddings else "unavailable",
        "stt": "deepgram" if settings.deepgram_api_key else "unavailable",
        "tts": settings.tts_provider
        if (
            (settings.tts_provider == "deepgram" and settings.deepgram_api_key)
            or (settings.tts_provider == "openai" and settings.openai_api_key)
        )
        else "unavailable",
    }
