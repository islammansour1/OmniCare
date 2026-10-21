"""Runtime dependency container.

Tests inject isolated singletons (temp SQLite/JSON/Chroma + deterministic
models) via ``set_runtime`` without touching the module-level singletons.
"""
from __future__ import annotations

from .agent.llm import get_language_model
from .claims import claims_store
from .db import db
from .deps import Deps
from .rag import pipeline

_runtime: Deps | None = None


def get_runtime() -> Deps:
    global _runtime
    if _runtime is None:
        _runtime = Deps(
            lm=get_language_model(),
            rag=pipeline,
            db=db,
            claims=claims_store,
        )
    return _runtime


def set_runtime(deps: Deps) -> None:
    global _runtime
    _runtime = deps


def reset_runtime() -> None:
    global _runtime
    _runtime = None
