"""SQLite persistence for conversation history and claim draft state.

Single writer-per-call connections keep it thread-safe under FastAPI's
threadpool without cross-thread SQLite connection sharing.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings
from .schemas import ClaimDraft

_write_lock = threading.Lock()


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else settings.database_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with _write_lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, updated REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turn_results (
                    scope TEXT NOT NULL, request_id TEXT NOT NULL, body_hash TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(scope, request_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message_type TEXT,
                    data_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id);

                CREATE TABLE IF NOT EXISTS drafts (
                    user_id TEXT PRIMARY KEY,
                    policy_number TEXT,
                    claim_type TEXT,
                    amount REAL,
                    description TEXT,
                    updated_ts REAL NOT NULL
                );
                """
            )

    # -- messages ----------------------------------------------------------
    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        message_type: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        with _write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(user_id, ts, role, content, message_type, data_json)"
                " VALUES(?,?,?,?,?,?)",
                (
                    user_id,
                    time.time(),
                    role,
                    content,
                    message_type,
                    json.dumps(data) if data is not None else None,
                ),
            )

    def get_messages(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, message_type, data_json FROM messages"
                " WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in reversed(rows):
            item: dict[str, Any] = {"id": str(r["id"]), "role": r["role"], "content": r["content"]}
            if r["message_type"]:
                item["message_type"] = r["message_type"]
            if r["data_json"]:
                item["data"] = json.loads(r["data_json"])
            out.append(item)
        return out

    def get_history(self, user_id: str, limit: int = 20) -> list[dict[str, str]]:
        """Compact {role, content} history for the agent context."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self.get_messages(user_id, limit)
            if m["role"] in ("user", "assistant")
        ]

    def clear(self, user_id: str) -> None:
        with _write_lock, self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))

    # -- drafts ------------------------------------------------------------
    def save_draft(self, user_id: str, draft: ClaimDraft) -> None:
        with _write_lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO drafts(user_id, policy_number, claim_type, amount, description, updated_ts)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(user_id) DO UPDATE SET"
                " policy_number=excluded.policy_number,"
                " claim_type=excluded.claim_type,"
                " amount=excluded.amount,"
                " description=excluded.description,"
                " updated_ts=excluded.updated_ts",
                (
                    user_id,
                    draft.policy_number,
                    draft.claim_type,
                    draft.amount,
                    draft.description,
                    time.time(),
                ),
            )

    def load_draft(self, user_id: str) -> ClaimDraft | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT policy_number, claim_type, amount, description FROM drafts WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return ClaimDraft(
            policy_number=row["policy_number"],
            claim_type=row["claim_type"],
            amount=row["amount"],
            description=row["description"],
        )

    def delete_draft(self, user_id: str) -> None:
        with _write_lock, self._connect() as conn:
            conn.execute("DELETE FROM drafts WHERE user_id=?", (user_id,))

    def issue_session(self, owner: str | None = None) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        owner = owner or "usr_" + uuid.uuid4().hex
        with _write_lock, self._connect() as conn:
            conn.execute("INSERT INTO sessions VALUES(?,?,?)", (
                hashlib.sha256(token.encode()).hexdigest(), owner, time.time() + 30*86400))
        return token, owner

    def session_owner(self, token: str) -> str | None:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT owner FROM sessions WHERE token_hash=? AND expires>?",
                               (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        return row['owner'] if row else None

    def create_conversation(self, owner: str) -> dict:
        item = {'id': uuid.uuid4().hex, 'title': 'New conversation', 'updated': time.time()}
        with _write_lock, self._connect() as conn:
            conn.execute('INSERT INTO conversations VALUES(?,?,?,?)',
                         (item['id'], owner, item['title'], item['updated']))
        return item

    def conversations(self, owner: str) -> list[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                'SELECT id,title,updated FROM conversations WHERE owner=? ORDER BY updated DESC', (owner,))]

    def resolve_scope(self, owner: str, conversation_id: str | None) -> str:
        if not conversation_id:
            return owner  # Legacy single-chat API remains isolated by authenticated owner.
        with self._connect() as conn:
            row = conn.execute('SELECT id FROM conversations WHERE owner=? AND id=?',
                               (owner, conversation_id)).fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(404, 'Conversation not found')
        return owner + ':' + conversation_id

    def update_conversation_activity(self, owner, conversation_id, message):
        if conversation_id:
            with _write_lock, self._connect() as conn:
                conn.execute("UPDATE conversations SET updated=?, title=CASE WHEN title='New conversation' THEN ? ELSE title END WHERE id=? AND owner=?",
                             (time.time(), message[:70], conversation_id, owner))

    def cached_turn(self, scope, request_id, body_hash):
        with self._connect() as conn:
            row = conn.execute('SELECT body_hash,response FROM turn_results WHERE scope=? AND request_id=?',
                               (scope, request_id)).fetchone()
        if row and row['body_hash'] != body_hash:
            from fastapi import HTTPException
            raise HTTPException(409, 'Request ID already used for a different message')
        return json.loads(row['response']) if row else None

    def cache_turn(self, scope, request_id, body_hash, response):
        with _write_lock, self._connect() as conn:
            conn.execute('INSERT OR REPLACE INTO turn_results VALUES(?,?,?,?)',
                         (scope, request_id, body_hash, json.dumps(response)))

    def record_turn(self, scope, message, response, request_id, body_hash):
        # History and replay cache commit together, avoiding duplicate turns after retries.
        with _write_lock, self._connect() as conn:
            for role, content, kind, data in (
                ('user', message, None, None),
                ('assistant', response['response'], response['message_type'], response)):
                conn.execute('INSERT INTO messages(user_id,ts,role,content,message_type,data_json) VALUES(?,?,?,?,?,?)',
                             (scope, time.time(), role, content, kind, json.dumps(data) if data else None))
            if request_id:
                conn.execute('INSERT INTO turn_results VALUES(?,?,?,?)',
                             (scope, request_id, body_hash, json.dumps(response)))


# Singleton (tests may construct isolated instances with a temp path).
db = Database()
