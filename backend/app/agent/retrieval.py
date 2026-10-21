"""Bounded evidence-driven retrieval; never retries to obtain a desired verdict."""
from typing import Any

from ..observability import log_event
from ..rag import RagPipeline
from .llm import LanguageModel


def assess_policy(
    lm: LanguageModel,
    rag: RagPipeline,
    question: str,
    history: list[dict[str, str]],
    initial_sources: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    # Keep the original wording as an independent search and as the assessment
    # input. A rewrite must never erase duration, negation, amounts or corrections.
    queries = [] if initial_sources else [question, lm.rewrite_query(question, history)]
    searched, evidence = set(), {s["id"]: s for s in (initial_sources or [])}
    analysis = None
    for round_number in range(3):
        before = len(evidence)
        for query in queries[:2]:
            key = query.strip().casefold()
            if not key or key in searched:
                continue
            searched.add(key)
            for source in rag.retrieve(query):
                evidence[source['id']] = source
        sources = list(evidence.values())
        if round_number and len(evidence) == before:
            break
        analysis = lm.analyze_policy(question, sources, history)
        queries = analysis.get('search_queries', [])
        # User clarification is allowed only after an explicit review of the
        # relevant grants, exclusions and conditions. Reviews share this budget.
        if not queries and (analysis['verdict'] == 'uncertain' or analysis.get('clarification')) and not analysis.get('needs_review'):
            review = lm.review_evidence(question, sources, history, analysis)
            log_event('rag.evidence_review', round=round_number + 1, sufficient=review.sufficient)
            if not review.sufficient or review.search_queries:
                queries = review.search_queries
                if not queries:
                    break
        log_event('rag.assessment', round=round_number + 1,
                  source_ids=list(evidence), needs_search=bool(queries))
        if not queries:
            return analysis, sources
    # The model explicitly requested missing evidence, but no further evidence
    # could be found within the budget. Never promote its provisional verdict.
    analysis = dict(analysis or {})
    analysis.update(verdict='uncertain' if analysis.get('facts') else 'unsupported',
                    clarification='I could not find enough policy evidence to resolve this. A policy review is needed.',
                    search_queries=[], needs_review=True)
    analysis.setdefault('facts', [])
    analysis.setdefault('cited_ids', [])
    return analysis, list(evidence.values())
