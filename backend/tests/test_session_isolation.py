"""Session isolation tests: drafts, history, and claims are all per-user."""
from __future__ import annotations

from app.agent.nodes import build_claim_status_node


def test_drafts_are_isolated_by_user(chat, client):
    chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    assert client.deps.db.load_draft("u1").claim_type == "Water Damage"
    assert client.deps.db.load_draft("u2") is None

    # u2's coverage question is unaffected by u1's in-flight draft.
    r = chat("u2", "Does my policy cover burst pipes?")
    assert r["message_type"] == "coverage_answer"
    assert r["data"]["verdict"] == "covered"

    # u2 files a different claim; the two drafts stay independent.
    chat("u2", "I want to file a claim for my stolen laptop")
    assert client.deps.db.load_draft("u2").claim_type == "Personal Property"
    assert client.deps.db.load_draft("u1").claim_type == "Water Damage"


def test_conversation_history_is_isolated(chat, client):
    chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    chat("u2", "Does my policy cover earthquakes?")

    u1_history = [m["content"] for m in client.deps.db.get_history("u1")]
    u2_history = [m["content"] for m in client.deps.db.get_history("u2")]

    assert any("burst pipe" in c for c in u1_history)
    assert not any("burst pipe" in c for c in u2_history)
    assert any("earthquakes" in c for c in u2_history)


def test_claim_lookup_is_isolated_by_owner(chat, client):
    created = client.deps.claims.submit_claim("POL-1092", "Water Damage", 3500.0, "pipe burst", owner_id="u1")
    cid = created["claim_id"]

    r1 = chat("u1", f"What is the status of claim {cid}?")
    assert r1["message_type"] == "claim_status"
    assert r1["data"]["claim"]["claim_id"] == cid

    # Another user cannot read u1's claim by id.
    r2 = chat("u2", f"What is the status of claim {cid}?")
    assert r2["message_type"] == "clarification"
    assert "claim" not in r2["data"]


def test_fresh_user_sees_no_claims(chat):
    # A brand-new identity owns nothing, so a status query yields no matches.
    r = chat("u1", "What is the status of my claims?")
    assert r["message_type"] == "claim_list"
    assert r["data"]["claims"] == []


def test_voice_claim_status_speaks_summary_not_picker(deps):
    # Voice (interactive=False) must read statuses aloud, never ask to "select".
    deps.claims.submit_claim("POL-1092", "Water Damage", 3500.0, "pipe burst", owner_id="u1")
    deps.claims.submit_claim("POL-3341", "Personal Property", 1200.0, "laptop", owner_id="u1")
    node = build_claim_status_node(deps, interactive=False)
    result = node({"message": "What is the status of my claims?", "owner_id": "u1"})["result"]
    assert result["message_type"] == "chat"
    assert "claim" in result["response"].lower()
    assert "select" not in result["response"].lower()


def test_voice_claim_status_no_matches(deps):
    node = build_claim_status_node(deps, interactive=False)
    result = node({"message": "What is the status of my claims?", "owner_id": "u1"})["result"]
    assert result["message_type"] == "chat"
    assert result["data"]["claims"] == []
