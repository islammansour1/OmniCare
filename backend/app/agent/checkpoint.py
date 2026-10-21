"""Process-wide persistent checkpointer for human-in-the-loop interrupts.

The chat graph pauses at ``interrupt()`` (claim confirmation / clarification)
and resumes on the next request via ``Command(resume=...)``. That pause state is
stored in a SQLite-backed ``SqliteSaver`` keyed by ``thread_id`` (= the
conversation scope). Voice turns are stateless and do not use a checkpointer.
"""
from __future__ import annotations

import sqlite3
import threading

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from ..config import settings

# Strict deserialization: only the built-in SAFE_MSGPACK_TYPES allowlist (49
# stdlib/langchain/langgraph types) may be reconstructed from a checkpoint.
# Without this, langgraph-checkpoint-sqlite defaults to a permissive msgpack
# mode that can be abused for code execution if the DB is ever compromised
# (see the langgraph-checkpoint-sqlite release notes / CVE-2025-64439).
_STRICT_SERDE = JsonPlusSerializer(allowed_msgpack_modules=None)

_checkpointers: dict[str, SqliteSaver] = {}
_lock = threading.Lock()


def build_checkpointer() -> SqliteSaver:
    """Return the ``SqliteSaver`` for the configured path (one per path, lazily).

    The saver serializes its own writes with an internal lock and uses a
    ``check_same_thread=False`` connection, so a single instance is safe to
    share across the request threadpool. The database file lives under the
    shared data directory alongside the application SQLite DB. Callers keyed by
    path keep isolated test runs (which monkeypatch the path) from leaking into
    the real store.
    """
    path = str(settings.checkpoint_file)
    saver = _checkpointers.get(path)
    if saver is None:
        with _lock:
            saver = _checkpointers.get(path)
            if saver is None:
                file = settings.checkpoint_file
                file.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(file), check_same_thread=False)
                saver = SqliteSaver(conn, serde=_STRICT_SERDE)
                saver.setup()
                _checkpointers[path] = saver
    return saver
