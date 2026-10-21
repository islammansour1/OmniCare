"""Human-in-the-loop interrupts: claim confirmation pauses and resumes.

The chat graph pauses at ``interrupt()`` in the claim-submit node and resumes on
the next request via ``Command(resume=...)``. These tests exercise that
round-trip with the deterministic test doubles and an isolated checkpointer.
"""
from __future__ import annotations

from unittest.mock import Mock

from app.agent.graph import run_agent


def _covered(**extra):
    return dict(verdict="covered", facts=["Evidence."], cited_ids=["sec1"],
                clarification="", search_queries=[], claim_requested=True,
                starts_new_incident=False, needs_review=False, **extra)


def _claim_deps(deps):
    deps.lm.classify_intent = Mock(return_value=("claim_submit", ""))
    deps.lm.analyze_policy = Mock(return_value=_covered())
    deps.lm.extract_claim_fields = Mock(return_value={"claim_type": "Water Damage",
                                                      "description": "Kitchen pipe burst"})
    return deps


def _checkpointer(tmp_path, monkeypatch):
    """Production checkpointer (strict serializer) on an isolated path."""
    from app.agent.checkpoint import build_checkpointer
    from app.config import settings

    monkeypatch.setattr(settings, "checkpoint_path", str(tmp_path / "checkpoint.sqlite"))
    return build_checkpointer()


def test_claim_submit_pauses_then_resumes_on_confirm(deps, tmp_path, monkeypatch):
    deps = _claim_deps(deps)
    cp = _checkpointer(tmp_path, monkeypatch)

    draft = run_agent("u1", "I want to file a claim for a burst pipe",
                      history=[], deps=deps, checkpointer=cp, thread_id="u1")
    assert draft["message_type"] == "claim_draft"
    assert draft["data"]["confirm_required"] is True
    assert draft["data"]["draft"]["claim_type"] == "Water Damage"

    edits = {"policy_number": "POL-1092", "claim_type": "Water Damage",
             "amount": 1200.0, "description": "Kitchen pipe burst"}
    confirmed = run_agent(
        "u1", "Confirm claim submission", action="confirm_submit", draft_input=edits,
        history=[{"role": "user", "content": "I want to file a claim for a burst pipe"}],
        deps=deps, checkpointer=cp, thread_id="u1",
        resume={"action": "confirm_submit", "draft": edits},
    )
    assert confirmed["message_type"] == "claim_confirmation"
    assert "claim_id" in confirmed["data"]["claim"]


def test_claim_submit_cancel_clears_draft(deps, tmp_path, monkeypatch):
    deps = _claim_deps(deps)
    cp = _checkpointer(tmp_path, monkeypatch)

    draft = run_agent("u1", "I want to file a claim", history=[], deps=deps,
                      checkpointer=cp, thread_id="u1")
    assert draft["message_type"] == "claim_draft"

    cancelled = run_agent(
        "u1", "Cancel claim submission", action="cancel_submit",
        history=[{"role": "user", "content": "I want to file a claim"}],
        deps=deps, checkpointer=cp, thread_id="u1",
        resume={"action": "cancel_submit", "draft": {}},
    )
    assert cancelled["message_type"] == "chat"
    assert cancelled["data"]["draft_cancelled"] is True


def test_stale_confirm_without_interrupt_falls_back_to_route(deps, tmp_path, monkeypatch):
    deps = _claim_deps(deps)
    cp = _checkpointer(tmp_path, monkeypatch)

    edits = {"policy_number": "POL-1092", "claim_type": "Water Damage",
             "amount": 1200.0, "description": "Kitchen pipe burst"}
    result = run_agent(
        "u1", "Confirm claim submission", action="confirm_submit", draft_input=edits,
        history=[], deps=deps, checkpointer=cp, thread_id="u1",
        resume={"action": "confirm_submit", "draft": edits},
    )
    # No draft was ever saved, so the confirm node reports nothing to submit
    # instead of raising on a missing interrupt.
    assert result["message_type"] == "clarification"
    assert result["data"]["question"] == "No claim draft to submit."


def test_voice_path_does_not_interrupt(deps):
    deps = _claim_deps(deps)
    # interactive=False (voice): the draft is returned directly, no checkpointer.
    result = run_agent("u1", "I want to file a claim", history=[], deps=deps,
                       interactive=False)
    assert result["message_type"] == "claim_draft"
    assert result["data"]["confirm_required"] is True
