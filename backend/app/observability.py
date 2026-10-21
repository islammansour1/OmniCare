"""Lightweight observability: request IDs, structured logging, timings.

Deliberately minimal — no external monitoring infrastructure. We log request
id, agent route, tool execution, retrieval source ids, latency, errors, and
token usage (when the provider reports it).
"""
from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any

from .config import settings

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())
    root.handlers = [handler]


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def new_request_id() -> str:
    rid = f"req_{uuid.uuid4().hex[:12]}"
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def log_event(event: str, **attrs: Any) -> None:
    logger = logging.getLogger("omnicare.event")
    logger.info("%s %s", event, attrs or "")
