"""Dependency bundle shared by the agent, service, and runtime container."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Deps:
    lm: Any
    rag: Any
    db: Any
    claims: Any
