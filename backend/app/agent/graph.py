"""Single LangGraph workflow shared by chat and voice.

Intent routing → retrieval / tool execution / structured extraction →
structured response. Confirmation requires an explicit user action and a policy preflight; writes
and cancellation are deterministic. The model cannot authorize a submission.
"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..deps import Deps
from .state import AgentState
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


def build_graph(deps: Deps):
    builder = StateGraph(AgentState)
    builder.add_node("route", build_route_node(deps))
    builder.add_node("coverage", build_coverage_node(deps))
    builder.add_node("claim_status", build_claim_status_node(deps))
    builder.add_node("claim_submit", build_claim_submit_node(deps))
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
    for n in ("coverage", "claim_status", "claim_submit", "confirm", "cancel", "chitchat"):
        builder.add_edge(n, END)
    return builder.compile()


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


def run_agent(
    user_id: str,
    message: str,
    action: str | None = None,
    draft_input: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
    deps: Deps | None = None,
    owner_id: str | None = None,
    on_progress=None,
) -> dict[str, Any]:
    deps = deps or get_deps()
    graph = build_graph(deps)
    state: AgentState = {
        "user_id": user_id,
        "owner_id": owner_id or user_id,
        "message": message,
        "action": action,
        "draft_input": draft_input,
        "history": history or [],
    }
    result = {}
    labels = {"route": "Understanding your request", "coverage": "Checking policy evidence",
              "claim_status": "Looking up claims", "claim_submit": "Preparing your draft",
              "confirm": "Saving your claim", "cancel": "Cancelling your draft"}
    for update in graph.stream(state, stream_mode="updates"):
        for node, values in update.items():
            if on_progress:
                on_progress(labels.get(node, "Preparing your response"))
            if values and "result" in values:
                result = values["result"]
    return result
