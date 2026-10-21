"""Hosted RAG evaluation for OmniCare.

Runs each golden case through the real ``RagPipeline`` (hosted embeddings via
``OpenAIEmbedder``) + the hosted policy analyzer (``get_language_model().analyze_policy``)
and reports:

- Retrieval Recall@K      — did ``expected_section_id`` appear in the top-K
                            retrieved sources (supported cases only).
- Verdict accuracy        — did ``expected_verdict`` match the hosted verdict.
- Citation validity       — every cited id exists in the policy chunks and, for
                            non-unsupported verdicts, matches the expected
                            required section(s); additional valid evidence is allowed.
- Unsupported handling    — unsupported queries must yield verdict
                            ``unsupported`` with zero citations.

A Markdown summary is written to ``results.md`` next to this file. Running the
evaluation requires hosted LLM + embedding credentials (Gemini, OpenAI, or
Anthropic); it fails fast rather than falling back to any offline substitute.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

GOLDEN_FILE = Path(__file__).resolve().parent / "golden_set.json"
RESULTS_FILE = Path(__file__).resolve().parent / "results.md"
POLICY_FILE = BACKEND_DIR.parent / "sample_policy.md"

TOP_K = 1

DEFAULT_MODE = "hosted embeddings + hosted policy analysis"

# Provider SDK retries handle transport failures. Never retry invalid evidence
# until the model happens to produce a passing answer: count it as a case error.

def load_golden_set(path: Path | None = None) -> list[dict]:
    """Load the golden dataset (a JSON array of cases)."""
    path = Path(path) if path else GOLDEN_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("golden set must be a JSON array")
    return data


def build_pipeline(chroma_dir=None, policy_file=None):
    """Build an isolated hosted RAG pipeline.

    Always supplies an explicit ``chroma_dir`` so the evaluation never touches
    the application's real Chroma directory under ``backend/data``.
    """
    from app.rag import OpenAIEmbedder, RagPipeline

    if chroma_dir is None:
        chroma_dir = Path(tempfile.mkdtemp(prefix="omnicare_eval_"))
    return RagPipeline(
        embedder=OpenAIEmbedder(),
        chroma_dir=Path(chroma_dir),
        policy_file=Path(policy_file) if policy_file else POLICY_FILE,
    )


def build_analyzer():
    """Return the hosted policy analyzer (``analyze_policy`` bound method)."""
    from app.agent.llm import get_language_model

    return get_language_model().analyze_policy


def evaluate_cases(cases, retrieve, valid_chunk_ids, top_k: int = TOP_K, analyzer=None) -> dict:
    """Score a list of golden cases against a ``retrieve(query) -> sources``
    callable and a hosted ``analyzer(question, sources, history) -> dict``."""
    if analyzer is None:
        analyzer = build_analyzer()

    valid_ids = set(valid_chunk_ids)
    per_case: list[dict] = []

    supported = 0
    recall_hits = 0
    verdict_hits = 0
    citation_ok = 0
    unsupported_total = 0
    unsupported_ok = 0
    error_count = 0

    for case in cases:
        query = case["query"]
        expected_verdict = case["expected_verdict"]
        expected_section = case.get("expected_section_id")

        history = case.get("history", [])
        sources = []
        error = None
        started = time.perf_counter()
        try:
            model = getattr(analyzer, '__self__', None)
            if model is not None:
                from types import SimpleNamespace
                from app.agent.retrieval import assess_policy
                analysis, sources = assess_policy(model, SimpleNamespace(retrieve=retrieve), query, history)
            else:
                # Scripted analyzers are used only for scorer accounting tests.
                sources = retrieve(query)
                analysis = analyzer(query, sources, history)
        except Exception as exc:
            error = type(exc).__name__
            error_count += 1
            analysis = {"verdict": "error", "cited_ids": []}
        verdict = analysis["verdict"]
        cited_ids = list(analysis.get("cited_ids") or [])
        retrieved_ids = [s["id"] for s in sources]

        # Recall@K is only meaningful for supported (non-unsupported) queries.
        is_supported = expected_verdict != "unsupported"
        recall = None
        if is_supported:
            supported += 1
            recall = expected_section in retrieved_ids[:top_k]
            recall_hits += 1 if recall else 0

        verdict_correct = verdict == expected_verdict
        verdict_hits += 1 if verdict_correct else 0

        # Citation validity: cited ids must be real chunks and, for supported
        # verdicts, must match the expected required section(s); additional valid evidence is allowed.
        cited_exist = all(cid in valid_ids for cid in cited_ids)
        # A wrong abstention cannot get credit for evidence it did not supply.
        expected_ids = set(case.get("expected_section_ids", [expected_section])) - {None}
        cited_match = (not cited_ids if expected_verdict == "unsupported"
                       else bool(cited_ids) and expected_ids <= set(cited_ids))
        citation_correct = error is None and cited_exist and cited_match
        citation_ok += 1 if citation_correct else 0

        # Unsupported handling: unsupported -> verdict unsupported, no cites.
        if expected_verdict == "unsupported":
            unsupported_total += 1
            if verdict == "unsupported" and cited_ids == []:
                unsupported_ok += 1

        per_case.append(
            {
                "id": case["id"],
                "query": query,
                "error": error,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "expected_verdict": expected_verdict,
                "expected_section_id": expected_section,
                "verdict": verdict,
                "retrieved_ids": retrieved_ids,
                "cited_ids": cited_ids,
                "recall": recall,
                "verdict_correct": verdict_correct,
                "citation_correct": citation_correct,
            }
        )

    metrics = {
        "errors": error_count,
        "top_k": top_k,
        "total": len(cases),
        "supported": supported,
        "recall_at_k": (recall_hits / supported) if supported else None,
        "verdict_accuracy": (verdict_hits / len(cases)) if cases else None,
        "citation_validity": (citation_ok / len(cases)) if cases else None,
        "unsupported_total": unsupported_total,
        "unsupported_handling": (unsupported_ok / unsupported_total) if unsupported_total else None,
    }
    return {"metrics": metrics, "per_case": per_case}


def run_eval(pipeline=None, cases=None, top_k: int = TOP_K, chroma_dir=None, analyzer=None) -> dict:
    """Build/ingest a hosted pipeline, run the golden set, and return results.

    ``pipeline`` and ``analyzer`` may be overridden (e.g. with offline fakes in
    tests); otherwise the hosted ``OpenAIEmbedder`` pipeline and
    ``get_language_model().analyze_policy`` are used.
    """
    cases = cases if cases is not None else load_golden_set()
    if pipeline is None:
        pipeline = build_pipeline(chroma_dir=chroma_dir)
    if analyzer is None:
        analyzer = build_analyzer()
    pipeline.ingest()
    chunk_ids = [c.id for c in pipeline.get_chunks()]
    return evaluate_cases(cases, pipeline.retrieve, chunk_ids, top_k=top_k, analyzer=analyzer)


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def format_summary(results: dict, mode: str = DEFAULT_MODE) -> str:
    """Render the evaluation results as a Markdown summary."""
    m = results["metrics"]
    lines = [
        "# OmniCare RAG Evaluation Results",
        "",
        f"- Mode: {mode}",
        f"- Golden cases: {m['total']} (supported: {m['supported']}, unsupported: {m['unsupported_total']})",
        f"- Top-K: {m['top_k']}",
        f"- Provider/validation errors: {m.get('errors', 0)}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Retrieval Recall@{m['top_k']} | {_pct(m['recall_at_k'])} |",
        f"| Verdict accuracy | {_pct(m['verdict_accuracy'])} |",
        f"| Citation validity | {_pct(m['citation_validity'])} |",
        f"| Unsupported-question handling | {_pct(m['unsupported_handling'])} |",
        "",
        "## Per-case results",
        "",
        "| id | query | expected | verdict | retrieved | cited | verdict_ok | citation_ok |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in results["per_case"]:
        retrieved = ",".join(c["retrieved_ids"]) or "—"
        cited = ",".join(c["cited_ids"]) or "—"
        lines.append(
            f"| {c['id']} | {c['query']} | {c['expected_verdict']} | {c['verdict']} "
            f"| {retrieved} | {cited} | {'Y' if c['verdict_correct'] else 'N'} "
            f"| {'Y' if c['citation_correct'] else 'N'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the hosted RAG evaluation.")
    parser.add_argument("--policy", default=str(POLICY_FILE), help="Policy Markdown or plain-text file")
    parser.add_argument("--golden", default=str(GOLDEN_FILE), help="Path to golden_set.json")
    parser.add_argument("--out", default=str(RESULTS_FILE), help="Path to write results.md")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Recall@K window size")
    args = parser.parse_args(argv)

    cases = load_golden_set(Path(args.golden))
    with tempfile.TemporaryDirectory(prefix="omnicare_eval_") as temp:
        results = run_eval(pipeline=build_pipeline(chroma_dir=Path(temp), policy_file=Path(args.policy)),
                           cases=cases, top_k=args.top_k)
    summary = format_summary(results)
    out = Path(args.out)
    out.write_text(summary, encoding="utf-8")
    print(summary)
    return 0 if passes_gate(results) else 1


def passes_gate(results):
    m = results['metrics']
    return (m.get('errors', 0) == 0 and m['verdict_accuracy'] is not None and m['verdict_accuracy'] >= 0.9
            and m['citation_validity'] >= 0.9
            and (m['recall_at_k'] is None or m['recall_at_k'] >= 0.9)
            and (m['unsupported_handling'] is None or m['unsupported_handling'] == 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
