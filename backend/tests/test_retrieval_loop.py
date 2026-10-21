from types import SimpleNamespace
from unittest.mock import Mock
from app.agent.retrieval import assess_policy
from app.agent.graph import build_claim_submit_node


def result(verdict='covered', queries=None):
    return dict(verdict=verdict, facts=['source evidence'], cited_ids=['a'],
                clarification='', search_queries=queries or [])


def test_searches_missing_evidence_then_revises_verdict():
    lm = SimpleNamespace(rewrite_query=Mock(return_value='normalized facts'),
                         analyze_policy=Mock(side_effect=[result(queries=['exceptions']), result('excluded')]))
    rag = SimpleNamespace(retrieve=Mock(side_effect=[
        [{'id':'a'}], [{'id':'a'}], [{'id':'b'}]]))
    analysis, sources = assess_policy(lm, rag, 'original duration and negation', [])
    assert analysis['verdict'] == 'excluded'
    assert [s['id'] for s in sources] == ['a','b']
    assert lm.analyze_policy.call_args.args[0] == 'original duration and negation'
    assert rag.retrieve.call_args.args[0] == 'exceptions'


def test_repeated_search_without_new_evidence_stops_without_accepting_provisional_verdict():
    lm = SimpleNamespace(rewrite_query=Mock(return_value='query'),
                         analyze_policy=Mock(return_value=result(queries=['query'])))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id':'a'}]))
    analysis, _ = assess_policy(lm, rag, 'query', [])
    assert analysis['verdict'] == 'uncertain'
    assert rag.retrieve.call_count == 1
    assert lm.analyze_policy.call_count == 1


def test_search_budget_is_bounded_even_when_new_evidence_keeps_arriving():
    lm = SimpleNamespace(rewrite_query=Mock(return_value='q0'),
                         analyze_policy=Mock(side_effect=[result(queries=[f'q{i}']) for i in range(1,4)]))
    rag = SimpleNamespace(retrieve=Mock(side_effect=[[{'id':str(i)}] for i in range(3)]))
    analysis, _ = assess_policy(lm, rag, 'q0', [])
    assert analysis['verdict'] == 'uncertain'
    assert lm.analyze_policy.call_count == 3
    assert rag.retrieve.call_count == 3


def test_extraction_cannot_remove_original_facts_or_skip_gate(deps):
    deps.lm.extract_claim_fields = Mock(return_value={})
    deps.lm.rewrite_query = Mock(return_value='water damage')
    deps.lm.analyze_policy = Mock(return_value=result('excluded'))
    message = 'My sink has been leaking for a while and it distroyed my home I need it fixed by your money'
    response = build_claim_submit_node(deps).invoke({'user_id':'test','owner_id':'test','message':message,'history':[]})['result']
    assert response['message_type'] == 'coverage_answer'
    assert response['data']['verdict'] == 'excluded'
    assert deps.lm.analyze_policy.call_args.args[0] == message


def test_edited_confirmation_rechecks_incident(chat, client):
    chat('edit-user', 'My policy is POL-1092 and my pipe burst causing about $3,500 in water damage')
    before = len(client.deps.claims.list_claims())
    response = chat('edit-user', 'Confirm', action='confirm_submit', draft={
        'description':'A gradual leak has damaged the floor over several months'})
    assert response['message_type'] == 'coverage_answer'
    assert response['data']['verdict'] == 'excluded'
    assert len(client.deps.claims.list_claims()) == before


def test_precomputed_query_skips_rewrite():
    lm = SimpleNamespace(rewrite_query=Mock(side_effect=AssertionError('should not rewrite')),
                         analyze_policy=Mock(return_value=result()))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id':'a'}]))
    analysis, sources = assess_policy(lm, rag, 'original', [], query='fused query')
    assert analysis['verdict'] == 'covered'
    # First search keeps the original wording; the fused query replaces the rewrite.
    assert [c.args[0] for c in rag.retrieve.call_args_list] == ['original', 'fused query']
    lm.rewrite_query.assert_not_called()


def test_evidence_review_expands_before_customer_clarification():
    lm = SimpleNamespace(
        rewrite_query=Mock(return_value='original'),
        analyze_policy=Mock(side_effect=[result('uncertain'), result('excluded')]),
        review_evidence=Mock(return_value=SimpleNamespace(sufficient=False, search_queries=['relevant exclusions'])))
    rag = SimpleNamespace(retrieve=Mock(side_effect=[[{'id':'a'}], [{'id':'b'}]]))
    analysis, sources = assess_policy(lm, rag, 'original', [])
    assert lm.review_evidence.call_count == 1
    assert rag.retrieve.call_args.args == ('relevant exclusions',)
    assert analysis['verdict'] == 'excluded'
    assert len(sources) == 2


def test_incomplete_policy_evidence_does_not_become_a_customer_question():
    lm = SimpleNamespace(
        rewrite_query=Mock(return_value='original'),
        analyze_policy=Mock(return_value=result('uncertain')),
        review_evidence=Mock(return_value=SimpleNamespace(sufficient=False, search_queries=[])))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id':'a'}]))
    analysis, _ = assess_policy(lm, rag, 'original', [])
    assert analysis['needs_review']
    assert lm.analyze_policy.call_count == 1


def test_user_clarification_survives_exhausted_review_search():
    # A user-facing question must not be discarded when document search is
    # exhausted: the remaining gap is a user fact, not a document gap.
    lm = SimpleNamespace(
        rewrite_query=Mock(return_value='original'),
        analyze_policy=Mock(return_value=dict(
            verdict='uncertain', facts=['source evidence'], cited_ids=['a'],
            clarification='What caused the damage?', search_queries=[])),
        review_evidence=Mock(return_value=SimpleNamespace(sufficient=False, search_queries=['missing clause'])))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id':'a'}]))  # no new evidence
    analysis, _ = assess_policy(lm, rag, 'original', [])
    assert analysis['clarification'] == 'What caused the damage?'
    assert analysis['needs_review'] is False
    assert analysis['verdict'] == 'uncertain'
    assert lm.review_evidence.call_count == 1
