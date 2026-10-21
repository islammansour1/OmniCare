"""Session isolation tests: drafts and history are per-user; claim lookup is
global (a shared read-only claims store)."""
from __future__ import annotations


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


def test_claim_lookup_is_global(chat):
    r1 = chat("u1", "What is the status of claim CLM-8821?")
    r2 = chat("u2", "What is the status of claim CLM-8821?")

    assert r1["message_type"] == "claim_status"
    assert r2["message_type"] == "claim_status"
    assert r1["data"]["claim"]["claim_id"] == "CLM-8821"
    assert r2["data"]["claim"]["claim_id"] == "CLM-8821"
