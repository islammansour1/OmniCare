"""Application configuration.

All providers are hosted and configurable via environment variables. Hosted
inference (LLM + embeddings) is the only path: the app fails fast with a clear
error when credentials are missing rather than falling back to any rule-based
or local substitute.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Mode -----------------------------------------------------------
    # Kept for backward compatibility; hosted inference is always required.
    omnicare_mode: str = "live"

    # --- Server ----------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"

    # --- Paths (resolved relative to backend/ unless absolute) ----------
    database_path: str = "./data/omnicare.db"
    claims_path: str = "./data/mock_claims.json"
    policy_path: str = "../sample_policy.md"
    chroma_path: str = "./data/chroma"
    checkpoint_path: str = "./data/checkpoint.db"

    # Explicit provider selection takes precedence over legacy provider keys.
    llm_provider: Literal["auto", "openai", "gemini", "anthropic", "openai-compatible"] = "auto"
    llm_api_key: str = ""
    llm_base_url: str = ""
    gemini_api_key: str = ""
    embedding_provider: Literal["auto", "openai", "gemini", "openai-compatible"] = "auto"

    # --- LLM (OpenAI-compatible) ----------------------------------------
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    # Optional Anthropic provider (used only when OPENAI_API_KEY is unset)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"

    # --- Embeddings (OpenAI-compatible endpoint) -------------------------
    embedding_model: str = ""
    embedding_api_key: str = ""  # falls back to openai_api_key
    embedding_base_url: str = ""  # falls back to openai_base_url

    # --- Speech-to-text (Deepgram) ---------------------------------------
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"

    # --- LiveKit real-time voice -------------------------------------------
    livekit_url: str = "ws://localhost:7880"
    # Internal address used by the backend/agent to reach the LiveKit server
    # (differs from `livekit_url` when running under docker). Falls back to it.
    livekit_internal_url: str = ""
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    livekit_agent_name: str = "omnicare-agent"

    # --- RAG --------------------------------------------------------------
    rag_hybrid_search: bool = True
    rag_top_k: int = 4
    rag_score_threshold: float = 0.05

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"

    # ----------------------------------------------------------------------
    def _resolve(self, p: str) -> Path:
        path = Path(p).expanduser()
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def database_file(self) -> Path:
        return self._resolve(self.database_path)

    @property
    def claims_file(self) -> Path:
        return self._resolve(self.claims_path)

    @property
    def policy_file(self) -> Path:
        return self._resolve(self.policy_path)

    @property
    def chroma_dir(self) -> Path:
        return self._resolve(self.chroma_path)

    @property
    def checkpoint_file(self) -> Path:
        return self._resolve(self.checkpoint_path)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_provider_config(self):
        if self.llm_provider == "auto" and self.llm_api_key:
            raise ValueError("Set LLM_PROVIDER when using LLM_API_KEY")
        if self.llm_provider == "openai-compatible" and not (self.llm_base_url and self.llm_model):
            raise ValueError("openai-compatible requires LLM_BASE_URL and LLM_MODEL")
        if self.embedding_provider == "openai-compatible" and not (self.embedding_base_url and self.embedding_model):
            raise ValueError("openai-compatible embeddings require EMBEDDING_BASE_URL and EMBEDDING_MODEL")
        if self.omnicare_mode.strip().lower() != "demo" and self.llm_provider != "auto" and not self.llm_api_key_resolved:
            raise ValueError("The selected LLM_PROVIDER requires LLM_API_KEY or its provider-specific key")
        return self

    @property
    def llm_provider_resolved(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        if self.gemini_api_key:
            return "gemini"
        return "openai"

    @property
    def llm_api_key_resolved(self) -> str:
        return self.llm_api_key or {
            "openai": self.openai_api_key,
            "openai-compatible": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
        }[self.llm_provider_resolved]

    @property
    def llm_base_url_resolved(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider_resolved == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        return self.openai_base_url

    @property
    def llm_model_resolved(self) -> str:
        return self.llm_model or {
            "gemini": "gemini-flash-latest",
            "anthropic": self.anthropic_model,
        }.get(self.llm_provider_resolved, "gpt-4o-mini")

    @property
    def embedding_provider_resolved(self) -> str:
        if self.embedding_provider != "auto":
            return self.embedding_provider
        # Preserve explicit legacy embedding configuration.
        if self.embedding_base_url or self.embedding_api_key:
            return "openai-compatible"
        return "gemini" if self.llm_provider_resolved == "gemini" else "openai"

    @property
    def embedding_model_resolved(self) -> str:
        return self.embedding_model or (
            "gemini-embedding-001" if self.embedding_provider_resolved == "gemini"
            else "text-embedding-3-small"
        )

    @property
    def embedding_api_key_resolved(self) -> str:
        if self.embedding_api_key:
            return self.embedding_api_key
        provider = self.embedding_provider_resolved
        if provider == self.llm_provider_resolved:
            return self.llm_api_key_resolved
        return self.gemini_api_key if provider == "gemini" else self.openai_api_key

    @property
    def embedding_base_url_resolved(self) -> str:
        if self.embedding_base_url:
            return self.embedding_base_url
        if self.embedding_provider_resolved == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        return self.openai_base_url

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key_resolved)

    @property
    def has_embeddings(self) -> bool:
        return bool(self.embedding_api_key_resolved)

    @property
    def resolved_mode(self) -> str:
        # Deterministic demo mode was removed: hosted inference is the only path.
        return "live"


@lru_cache
def get_settings() -> Settings:
    # Ensure Chroma never instantiates its built-in (local) embedding model.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    return Settings()


settings = get_settings()
