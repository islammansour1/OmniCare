"""LangGraph Studio entry point (development tooling only).

This module exists solely so LangGraph Studio — run locally with
``langgraph dev`` — can load and visualize the agent graph. It is not part of
the application runtime and is never imported by the API, tests, or evals.
"""

from pathlib import Path
import sys

# Make `app` importable regardless of the working directory the dev server uses.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agent.graph import build_graph, get_deps  # noqa: E402

# Compiled graph, with hosted dependencies baked in once at load time.
graph = build_graph(get_deps())
