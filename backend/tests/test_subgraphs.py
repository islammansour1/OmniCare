"""The policy workflow must remain inspectable as a real LangGraph subgraph."""
from types import SimpleNamespace

from app.agent.graph import build_graph


def test_policy_workflow_is_exposed_as_a_langgraph_subgraph():
    graph = build_graph(SimpleNamespace(lm=None, rag=None, db=None, claims=None))
    coverage = dict(graph.get_subgraphs())["coverage"]
    policy = dict(coverage.get_subgraphs())["policy_assessment"]
    edges = {(edge.source, edge.target) for edge in policy.get_graph().edges}
    assert ("rewrite_query", "retrieve") in edges
    assert ("retrieve", "assess") in edges
    assert ("assess", "retrieve") in edges
