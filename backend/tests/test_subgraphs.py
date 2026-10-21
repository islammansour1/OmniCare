"""The ``coverage`` and ``claim_submit`` intents are compiled as named subgraphs.

LangGraph Studio (and the parent graph) should see their finer-grained internal
steps rather than a single box per intent, while the top-level node names stay
frozen for routing and SSE progress labels.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.agent.graph import build_graph
from app.agent.nodes import build_claim_submit_node, build_coverage_node


def _deps():
    return SimpleNamespace(lm=None, rag=None, db=None, claims=None)


def test_top_level_node_names_are_frozen():
    graph = build_graph(_deps())
    names = sorted(graph.get_graph().nodes.keys())
    assert names == [
        "__end__", "__start__", "cancel", "chitchat", "claim_status",
        "claim_submit", "confirm", "coverage", "route",
    ]


def test_coverage_is_an_assess_then_compose_subgraph():
    subgraph = build_coverage_node(_deps())
    assert sorted(subgraph.nodes.keys()) == ["__start__", "assess", "compose"]


def test_claim_submit_is_a_fan_out_then_join_subgraph():
    subgraph = build_claim_submit_node(_deps())
    assert sorted(subgraph.nodes.keys()) == [
        "__start__", "assess_coverage", "compose", "extract_fields", "prepare",
    ]


def test_parent_graph_exposes_both_as_subgraphs():
    graph = build_graph(_deps())
    subgraphs = dict(graph.get_subgraphs())
    assert sorted(subgraphs) == ["claim_submit", "coverage"]
    assert sorted(subgraphs["coverage"].nodes.keys()) == ["__start__", "assess", "compose"]
    assert sorted(subgraphs["claim_submit"].nodes.keys()) == [
        "__start__", "assess_coverage", "compose", "extract_fields", "prepare",
    ]
