"""Explicit policy workflow, shared by coverage, claim gates and voice."""
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from ..observability import log_event
from ..rag import RagPipeline
from .llm import LanguageModel


class PolicyState(TypedDict, total=False):
    message: str
    history: list[dict[str, str]]
    query: str
    initial_sources: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    assessment: dict[str, Any]
    pending_queries: list[str]
    searched_queries: list[str]
    retrieval_round: int
    exhausted: bool


class PolicyOutput(TypedDict):
    query: str
    sources: list[dict[str, Any]]
    assessment: dict[str, Any]


def build_policy_graph(lm: LanguageModel, rag: RagPipeline):
    """Rewrite → retrieve → assess; branch to evidence review or bounded search.

    A customer fact gap exits with a clarification assessment. A document gap
    loops through retrieval, never through customer questioning. Caller-facing
    outputs exclude internal search counters so parallel claim branches don't
    write overlapping state.
    """
    builder = StateGraph(PolicyState, output_schema=PolicyOutput)

    def rewrite(state):
        query = state.get('query') or lm.rewrite_query(state['message'], state.get('history', []))
        return dict(query=query, pending_queries=[query], searched_queries=[],
                    retrieval_round=0, sources=state.get('initial_sources') or [], exhausted=False)

    def retrieve(state):
        evidence = {s['id']: s for s in state['sources']}
        before = len(evidence)
        searched = set(state['searched_queries'])
        for query in state['pending_queries'][:2]:
            key = query.strip().casefold()
            if key and key not in searched:
                searched.add(key)
                for source in rag.retrieve(query):
                    evidence[source['id']] = source
        rounds = state['retrieval_round'] + 1
        return dict(sources=list(evidence.values()), searched_queries=sorted(searched),
                    retrieval_round=rounds, exhausted=rounds > 1 and len(evidence) == before)

    def assess(state):
        analysis = lm.analyze_policy(state['message'], state['sources'], state.get('history', []))
        queries = analysis.get('search_queries', [])
        log_event('rag.assessment', round=state['retrieval_round'],
                  source_ids=[s['id'] for s in state['sources']], needs_search=bool(queries))
        return dict(assessment=analysis, pending_queries=queries)

    def after_assess(state):
        analysis = state['assessment']
        if state['pending_queries']:
            return 'retrieve' if state['retrieval_round'] < 3 else 'insufficient_evidence'
        if ((analysis['verdict'] == 'uncertain' or analysis.get('clarification'))
                and not analysis.get('needs_review')):
            return 'review_evidence'
        return END

    def review(state):
        analysis = state['assessment']
        result = lm.review_evidence(state['message'], state['sources'], state.get('history', []), analysis)
        log_event('rag.evidence_review', round=state['retrieval_round'], sufficient=result.sufficient)
        return dict(pending_queries=result.search_queries,
                    exhausted=not result.sufficient and not result.search_queries)

    def after_review(state):
        if state['exhausted']:
            return 'insufficient_evidence'
        if state['pending_queries']:
            return 'retrieve' if state['retrieval_round'] < 3 else 'insufficient_evidence'
        return END

    def insufficient(state):
        analysis = dict(state.get('assessment') or {})
        analysis.update(verdict='uncertain' if analysis.get('facts') else 'unsupported',
                        clarification='', clarification_terms=[], search_queries=[], needs_review=True)
        analysis.setdefault('facts', [])
        analysis.setdefault('cited_ids', [])
        return {'assessment': analysis}

    builder.add_node('rewrite_query', rewrite)
    builder.add_node('retrieve', retrieve)
    builder.add_node('assess', assess)
    builder.add_node('review_evidence', review)
    builder.add_node('insufficient_evidence', insufficient)
    builder.add_edge(START, 'rewrite_query')
    builder.add_edge('rewrite_query', 'retrieve')
    builder.add_conditional_edges('retrieve', lambda s: 'insufficient_evidence' if s['exhausted'] else 'assess',
                                  ['insufficient_evidence', 'assess'])
    builder.add_conditional_edges('assess', after_assess, ['retrieve', 'review_evidence', 'insufficient_evidence', END])
    builder.add_conditional_edges('review_evidence', after_review, ['retrieve', 'insufficient_evidence', END])
    builder.add_edge('insufficient_evidence', END)
    return builder.compile(name='policy_assessment')


def assess_policy(lm, rag, question, history, initial_sources=None, query=None):
    """Convenience entry point; all policy control flow lives in LangGraph."""
    result = build_policy_graph(lm, rag).invoke(dict(
        message=question, history=history, query=query or '', initial_sources=initial_sources or []))
    return result['assessment'], result['sources']
