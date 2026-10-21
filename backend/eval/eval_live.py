"""Opt-in hosted embedding AND policy-analysis evaluation. Never silently skips.

Thin wrapper over the hosted ``eval_runner``: checks credentials, runs the real
hosted evaluation, writes a Markdown summary, and exits nonzero when
credentials are missing or the quality gates fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from eval_runner import format_summary, load_golden_set, passes_gate, run_eval  # noqa: E402


def main() -> int:
    from app.config import settings

    if not settings.has_llm or not settings.has_embeddings:
        print("NOT RUN: hosted LLM and embedding credentials are required in live mode.")
        return 2

    results = run_eval(cases=load_golden_set())
    summary = format_summary(
        results,
        mode="hosted embeddings + hosted policy analysis: " + settings.llm_model_resolved,
    )
    Path(__file__).with_name("results_live.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if passes_gate(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
