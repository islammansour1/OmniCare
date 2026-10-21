"""Shared test fixtures.

All tests run against isolated temp storage (SQLite/JSON/Chroma) and the
deterministic test doubles (``FakeLanguageModel`` + ``FakeEmbedder``) — no
network, no hosted inference, and the real sample claims file is never mutated.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from fakes import FakeEmbedder, FakeLanguageModel

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
SAMPLE_CLAIMS = BACKEND / "data" / "mock_claims.json"
POLICY_FILE = ROOT / "sample_policy.md"


def make_deps(tmp_path: Path):
    """Construct an isolated dependency bundle for the shared workflow."""
    from app.claims import ClaimsStore
    from app.db import Database
    from app.deps import Deps
    from app.rag import RagPipeline

    claims_file = tmp_path / "claims.json"
    shutil.copy(SAMPLE_CLAIMS, claims_file)

    return Deps(
        lm=FakeLanguageModel(),
        rag=RagPipeline(
            embedder=FakeEmbedder(),
            chroma_dir=tmp_path / "chroma",
            policy_file=POLICY_FILE,
        ),
        db=Database(tmp_path / "db.sqlite"),
        claims=ClaimsStore(claims_file),
    )


@pytest.fixture()
def deps(tmp_path):
    return make_deps(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """FastAPI TestClient wired to isolated dependencies."""
    from app.config import settings

    # Ensure no provider credentials leak into the test process (defensive).
    for key in ("llm_api_key", "gemini_api_key", "openai_api_key",
                "anthropic_api_key", "embedding_api_key", "deepgram_api_key"):
        monkeypatch.setattr(settings, key, "")

    deps = make_deps(tmp_path)
    from app.runtime import set_runtime

    set_runtime(deps)

    from fastapi.testclient import TestClient

    from app.main import app

    class AuthenticatedTestClient(TestClient):
        def post(self, url, **kwargs):
            # Existing fixtures use named users. Issue real opaque credentials for
            # those identities; explicit headers let security tests bypass this.
            if url.startswith('/api/v1/chat') and 'headers' not in kwargs:
                owner = kwargs.get('json', {}).get('user_id', 'u1')
                token, _ = deps.db.issue_session(owner)
                kwargs['headers'] = {'Authorization': 'Bearer ' + token}
            return super().post(url, **kwargs)

    with AuthenticatedTestClient(app) as c:
        c.deps = deps  # expose for assertions
        yield c

    from app.runtime import reset_runtime

    reset_runtime()


@pytest.fixture()
def claims_path(tmp_path):
    p = tmp_path / "claims.json"
    shutil.copy(SAMPLE_CLAIMS, p)
    return p


def read_claims(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def chat(client):
    """Post a single chat turn to the isolated app and return the JSON body."""

    def _post(user_id, message, *, action=None, draft=None, request_id=None):
        payload = {"user_id": user_id, "message": message}
        if action is not None:
            payload["action"] = action
        if draft is not None:
            payload["draft"] = draft
        if request_id is not None:
            payload["request_id"] = request_id
        r = client.post("/api/v1/chat", json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    return _post
