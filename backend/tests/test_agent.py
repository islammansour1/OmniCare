"""LangGraph agent workflow tests (via the isolated HTTP client).

Covers multi-turn claim extraction, intent switching, draft editing,
cancellation, explicit-confirmation gating, idempotent confirmation, and
greeting handling.
"""
from __future__ import annotations


def test_multi_turn_claim_extraction(chat):
    r1 = chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    assert r1["message_type"] == "claim_draft"
    assert r1["data"]["draft"]["claim_type"] == "Water Damage"
    assert r1["data"]["draft"]["policy_number"] is None
    assert r1["data"]["draft"]["amount"] is None
    assert set(r1["data"]["missing_fields"]) == {"policy_number", "amount"}

    r2 = chat("u1", "My policy is POL-1092 and the damage is about $3,500")
    assert r2["message_type"] == "claim_draft"
    draft = r2["data"]["draft"]
    assert draft["policy_number"] == "POL-1092"
    assert draft["amount"] == 3500.0
    assert draft["claim_type"] == "Water Damage"  # accumulated from turn 1
    assert r2["data"]["missing_fields"] == []

    # Missing fields shrink across turns.
    assert len(r1["data"]["missing_fields"]) > len(r2["data"]["missing_fields"])


def test_intent_switching_preserves_draft(chat, client):
    r1 = chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    assert r1["message_type"] == "claim_draft"
    assert r1["data"]["draft"]["claim_type"] == "Water Damage"

    # Unrelated coverage question mid-flow.
    r2 = chat("u1", "Does my policy cover earthquakes?")
    assert r2["message_type"] == "coverage_answer"
    assert r2["data"]["verdict"] == "unsupported"

    # The draft must survive the detour.
    draft = client.deps.db.load_draft("u1")
    assert draft is not None
    assert draft.claim_type == "Water Damage"

    # Return and finish the claim.
    r3 = chat("u1", "My policy is POL-1092 and the damage is about $3,500")
    assert r3["message_type"] == "claim_draft"
    assert r3["data"]["missing_fields"] == []
    assert r3["data"]["draft"]["policy_number"] == "POL-1092"
    assert r3["data"]["draft"]["claim_type"] == "Water Damage"


def test_editing_draft_on_confirm(chat):
    chat("u1", "My policy is POL-1092 and my pipe burst causing about $3,500 in water damage")

    edited = {
        "policy_number": "POL-1092",
        "claim_type": "Water Damage",
        "amount": 4200.0,
        "description": "A pipe burst in the basement caused heavy water damage",
    }
    r = chat("u1", "Confirm", action="confirm_submit", draft=edited)
    assert r["message_type"] == "claim_confirmation"
    claim = r["data"]["claim"]
    assert claim["amount"] == 4200.0
    assert claim["description"] == edited["description"]
    assert claim["policy_number"] == "POL-1092"


def test_cancellation_clears_draft(chat, client):
    chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    assert client.deps.db.load_draft("u1") is not None

    r = chat("u1", "Never mind", action="cancel_submit")
    assert r["message_type"] == "chat"
    assert client.deps.db.load_draft("u1") is None


def test_full_info_without_action_does_not_submit(chat, client):
    r = chat(
        "u1",
        "My policy is POL-1092 and my pipe burst causing about $3,500 in water damage",
    )
    assert r["message_type"] == "claim_draft"
    assert r["data"]["confirm_required"] is True
    assert r["data"]["missing_fields"] == []
    # No claim was created without an explicit confirm action.
    assert len(client.deps.claims.list_claims()) == 0


def test_confirmation_executes_exactly_once(chat, client):
    d = chat("u1", "My policy is POL-1092 and my pipe burst causing about $3,500 in water damage")
    draft = d["data"]["draft"]

    c1 = chat("u1", "Confirm", action="confirm_submit", draft=draft)
    assert c1["message_type"] == "claim_confirmation"
    claim_id = c1["data"]["claim"]["claim_id"]
    assert claim_id.startswith("CLM-")
    assert len(client.deps.claims.list_claims()) == 1  # only the new claim

    # Replay the same confirmation (draft is now gone) -> same id, no duplicate.
    c2 = chat("u1", "Confirm", action="confirm_submit", draft=draft)
    assert c2["message_type"] == "claim_confirmation"
    assert c2["data"]["claim"]["claim_id"] == claim_id
    assert len(client.deps.claims.list_claims()) == 1


def test_greeting(chat):
    r = chat("hello_user", "hello")
    assert r["message_type"] == "greeting"


def test_claim_draft_blocks_excluded_gradual_leak(chat):
    # "leak" with no sudden cause must be flagged, not silently drafted.
    r = chat("u1", "My sink is leaking and I want to file a claim for the water damage")
    assert r["message_type"] == "coverage_answer"
    assert r["data"]["verdict"] == "excluded"


def test_claim_draft_blocks_explicit_slow_leak(chat):
    r = chat("u1", "There's a slow leak that's been going on for months — I want to file a claim")
    assert r["message_type"] == "coverage_answer"
    assert r["data"]["verdict"] == "excluded"


def test_burst_pipe_claim_still_drafts(chat):
    # A sudden-cause claim is the covered happy path and must keep drafting.
    r = chat("u1", "I want to file a claim for a burst pipe in my kitchen")
    assert r["message_type"] == "claim_draft"
