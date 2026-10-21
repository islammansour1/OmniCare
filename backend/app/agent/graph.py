"""Single LangGraph workflow shared by chat and voice.

Intent routing → retrieval / tool execution / structured extraction →
structured response. Confirmation requires an explicit user action and a policy preflight; writes
and cancellation are deterministic. The model cannot authorize a submission.
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..deps import Deps
from .state import AgentInput, AgentState
from .nodes import (
    build_route_node,
    build_coverage_node,
    build_claim_status_node,
    build_claim_submit_node,
    build_confirm_node,
    build_cancel_node,
    build_chitchat_node,
)

logger = logging.getLogger("omnicare.agent")


# ---------------------------------------------------------------------------
# Graph wiring
# ---------------------------------------------------------------------------


def _after_claim_submit(state: AgentState) -> str:
    """Route a claim draft that just resumed from its confirmation interrupt.

    ``claim_submit`` (and the ``coverage`` node, which delegates to it) normally
    returns a terminal ``result`` and the turn ends. When it instead pauses for
    confirmation and later resumes, it emits ``intent=confirm|cancel`` and the
    turn continues into the matching node.
    """
    intent = state.get("intent")
    if intent == "confirm":
        return "confirm"
    if intent == "cancel":
        return "cancel"
    return "done"


def build_graph(deps: Deps, checkpointer=None, interactive: bool = True):
    builder = StateGraph(AgentState, input_schema=AgentInput)
    builder.add_node("route", build_route_node(deps))
    builder.add_node("coverage", build_coverage_node(deps))
    builder.add_node("claim_status", build_claim_status_node(deps))
    builder.add_node("claim_submit", build_claim_submit_node(deps, interactive=interactive))
    builder.add_node("confirm", build_confirm_node(deps))
    builder.add_node("cancel", build_cancel_node(deps))
    builder.add_node("chitchat", build_chitchat_node(deps))

    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        lambda s: s["intent"],
        {
            "coverage": "coverage",
            "claim_status": "claim_status",
            "claim_submit": "claim_submit",
            "confirm": "confirm",
            "cancel": "cancel",
            "chitchat": "chitchat",
        },
    )
    # A claim draft pauses for confirmation and, on resume, routes into
    # confirm/cancel. Both entry points (route → claim_submit, and coverage →
    # nested claim_submit) need this edge.
    for n in ("coverage", "claim_submit"):
        builder.add_conditional_edges(
            n,
            _after_claim_submit,
            {"confirm": "confirm", "cancel": "cancel", "done": END},
        )
    for n in ("claim_status", "confirm", "cancel", "chitchat"):
        builder.add_edge(n, END)
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_DEFAULT_DEPS: Deps | None = None


def get_deps() -> Deps:
    global _DEFAULT_DEPS
    if _DEFAULT_DEPS is None:
        from ..claims import claims_store
        from ..db import db
        from ..rag import pipeline
        from .llm import get_language_model

        _DEFAULT_DEPS = Deps(
            lm=get_language_model(),
            rag=pipeline,
            db=db,
            claims=claims_store,
        )
    return _DEFAULT_DEPS


_LABELS = {"route": "Understanding your request", "coverage": "Checking policy evidence",
           "claim_status": "Looking up claims", "claim_submit": "Preparing your draft",
           "confirm": "Saving your claim", "cancel": "Cancelling your draft"}


def run_agent(
    user_id: str,
    message: str,
    action: str | None = None,
    draft_input: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    deps: Deps | None = None,
    owner_id: str | None = None,
    on_progress=None,
    checkpointer=None,
    thread_id: str | None = None,
    resume: dict[str, Any] | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    """Run one turn of the agent, resuming a paused interrupt when possible.

    ``thread_id`` keys the checkpointer (the conversation scope). ``resume``
    carries the human decision for a pending ``interrupt()``. Returns the final
    ``result`` dict, or the interrupt payload when the turn paused mid-flight.
    """
    deps = deps or get_deps()
    graph = build_graph(deps, checkpointer=checkpointer, interactive=interactive)
    config = {"configurable": {"thread_id": thread_id}} if thread_id else {}

    result: dict[str, Any] = {}

    def _collect(update) -> None:
        nonlocal result
        for node, values in update.items():
            if node == "__interrupt__":
                # A node paused on interrupt(); its value IS the turn's payload.
                # The only interrupt in this graph is the claim-confirmation
                # pause, so surface its progress label here.
                interrupts = values if isinstance(values, (tuple, list)) else (values,)
                if interrupts:
                    result = interrupts[0].value
                if on_progress:
                    on_progress(_LABELS["claim_submit"])
                continue
            if on_progress:
                on_progress(_LABELS.get(node, "Preparing your response"))
            if isinstance(values, dict) and "result" in values:
                result = values["result"]

    # Resume a pending interrupt (human decision) when one exists; otherwise
    # fall back to a fresh run (the route node handles the action flag).
    resumed = False
    if resume is not None and checkpointer is not None and thread_id is not None:
        snapshot = graph.get_state(config)
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            for update in graph.stream(Command(resume=resume), stream_mode="updates", config=config):
                _collect(update)
            resumed = True

    if not resumed:
        state: AgentState = {
            "user_id": user_id,
            "owner_id": owner_id or user_id,
            "message": message,
            "action": action,
            "draft_input": draft_input,
            "history": history or [],
        }
        for update in graph.stream(state, stream_mode="updates", config=config):
            _collect(update)

    if result:
        return result

    # No terminal result: a node paused on a human-in-the-loop interrupt.
    if checkpointer is not None and thread_id is not None:
        snapshot = graph.get_state(config)
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            return snapshot.tasks[0].interrupts[0].value

    return result
