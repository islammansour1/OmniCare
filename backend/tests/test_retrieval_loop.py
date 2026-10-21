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
        [{'id':'a'}], [{'id':'b'}]]))
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


def test_failed_document_review_cannot_be_overridden_by_proposed_question():
    # The reviewer still needs a clause: a proposed question cannot turn this
    # document gap into a customer fact gap.
    lm = SimpleNamespace(
        rewrite_query=Mock(return_value='original'),
        analyze_policy=Mock(return_value=dict(
            verdict='uncertain', facts=['source evidence'], cited_ids=['a'],
            clarification='What caused the damage?', search_queries=[])),
        review_evidence=Mock(return_value=SimpleNamespace(sufficient=False, search_queries=['missing clause'])))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id':'a'}]))  # no new evidence
    analysis, _ = assess_policy(lm, rag, 'original', [])
    assert analysis['clarification'] == ''
    assert analysis['needs_review'] is True
    assert analysis['verdict'] == 'uncertain'
    assert lm.review_evidence.call_count == 1


def test_followup_searches_new_facts_even_with_cached_evidence():
    lm = SimpleNamespace(rewrite_query=Mock(return_value='new incident fact'),
                         analyze_policy=Mock(return_value=result('excluded')))
    rag = SimpleNamespace(retrieve=Mock(return_value=[{'id': 'new'}]))
    _, sources = assess_policy(lm, rag, 'new incident fact', [], initial_sources=[{'id': 'old'}])
    rag.retrieve.assert_called_once_with('new incident fact')
    assert {s['id'] for s in sources} == {'old', 'new'}


def test_supported_customer_question_follows_retrieval_and_review():
    stages = []
    def retrieve(query):
        stages.append('retrieve')
        return [{'id': 'a'}]
    def assess(*args):
        stages.append('assess')
        return {**result('uncertain'), 'clarification': 'Where was the item stored?'}
    def review(*args):
        stages.append('review')
        return SimpleNamespace(sufficient=True, search_queries=[])
    lm = SimpleNamespace(analyze_policy=assess, review_evidence=review)
    analysis, _ = assess_policy(lm, SimpleNamespace(retrieve=retrieve), 'incident', [], query='incident')
    assert stages == ['retrieve', 'assess', 'review']
    assert analysis['clarification'] == 'Where was the item stored?'
