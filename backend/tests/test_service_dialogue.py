from unittest.mock import Mock
from app.agent.graph import run_agent
from app.db import Database


def analysis(verdict='uncertain', question='How did the damage happen?', **extra):
    return dict(verdict=verdict, facts=['Evidence.'], cited_ids=['sec1'],
                clarification=question if verdict=='uncertain' else '', search_queries=[], **extra)


def turn(deps, message):
    result = run_agent('dialogue', message, history=deps.db.get_history('dialogue'), deps=deps)
    deps.db.record_turn('dialogue', message, result, None, '')
    return result


def test_short_questions_reuse_evidence_and_stop_after_two_even_after_restart(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(side_effect=[analysis(), analysis(question='Do you know the source?'), analysis(), analysis()])
    deps.rag.retrieve = Mock(wraps=deps.rag.retrieve)
    first = turn(deps,'Actual damage needs assessment')
    assert first['message_type'] == 'clarification'
    assert first['response'] == 'How did the damage happen?'
    assert first['sources'] == []
    calls = deps.rag.retrieve.call_count
    deps.db = Database(deps.db.path)
    second = turn(deps,'It happened this morning')
    assert second['message_type'] == 'clarification'
    assert deps.rag.retrieve.call_count == calls
    third = turn(deps,'Not sure')
    fourth = turn(deps,'Still not sure')
    for result in (third,fourth):
        assert result['message_type'] == 'coverage_answer'
        assert '?' not in result['response']
        assert result['data']['policy_dialogue']['questions'] == 2


def test_resolved_claim_request_moves_to_form_without_reassessing(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis('covered', claim_requested=True))
    deps.lm.extract_claim_fields = Mock(return_value={'description':'User confirmed the cause'})
    r = turn(deps, 'Yes, that is what happened')
    assert r['message_type'] == 'claim_draft'
    assert r['sources'][0]['id'] == 'sec1'
    assert deps.lm.analyze_policy.call_count == 1
    assert r['data']['confirm_required']


def test_general_policy_question_does_not_open_claim_form(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis('covered', claim_requested=False))
    assert turn(deps,'General policy question')['message_type'] == 'coverage_answer'


def test_repeated_question_stops_and_new_incident_resets_budget(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(side_effect=[analysis(), analysis(), analysis(starts_new_incident=True)])
    assert turn(deps,'An incident')['message_type'] == 'clarification'
    assert turn(deps,'An unclear reply')['message_type'] == 'coverage_answer'
    r = turn(deps,'A different incident')
    assert r['message_type'] == 'clarification'
    assert r['data']['policy_dialogue']['questions'] == 1


def test_explicit_unknown_can_stop_without_more_questions(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis(question='', needs_review=True))
    r = turn(deps,'I cannot tell what happened')
    assert r['message_type'] == 'coverage_answer'
    assert '?' not in r['response']
    assert r['data']['policy_dialogue']['questions'] == 2


def test_clarification_passes_review_then_final_writing_layer(deps):
    stages = []
    from types import SimpleNamespace
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis(question='Internal missing-fact question'))
    def review(*args):
        stages.append('review')
        return SimpleNamespace(sufficient=True, search_queries=[])
    def compose(message, missing, sources, history):
        stages.append('compose')
        assert missing == 'Internal missing-fact question'
        assert sources
        return "I'm sorry about the damage. Did it happen suddenly or develop over time?"
    deps.lm.review_evidence = review
    deps.lm.compose_clarification = compose
    r = turn(deps,'My floor is damaged')
    assert stages == ['review','compose']
    assert r['response'] == r['data']['question']
    assert "I'm sorry" in r['response']
    assert 'Internal missing-fact' not in r['response']


def test_route_fused_query_is_used_for_retrieval_without_rewrite(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', 'fused query'))
    deps.lm.analyze_policy = Mock(return_value=analysis('covered', claim_requested=False))
    deps.lm.rewrite_query = Mock(side_effect=AssertionError('rewrite should not be called'))
    deps.rag.retrieve = Mock(wraps=deps.rag.retrieve)
    turn(deps, 'my pipe burst')
    assert any(c.args[0] == 'fused query' for c in deps.rag.retrieve.call_args_list)
    deps.lm.rewrite_query.assert_not_called()


def test_terminal_uncertainty_keeps_policy_details_and_citations(deps):
    deps.rag.retrieve = Mock(return_value=[{'id':'sec1', 'section':'Relevant policy',
                                          'text':'Coverage terms. Relevant exclusion.'}])
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    decision = analysis(question='Do not ask this again?', needs_review=True)
    decision['facts'] = ['Coverage terms.', 'Relevant exclusion.']
    deps.lm.analyze_policy = Mock(return_value=decision)
    deps.lm.compose_answer = Mock(return_value='Coverage terms. Relevant exclusion. The cause remains unclear.')
    r = turn(deps,'I think it was slow then all at once')
    assert r['message_type'] == 'coverage_answer'
    assert r['data']['verdict'] == 'uncertain'
    assert r['response'] == deps.lm.compose_answer.return_value
    assert '?' not in r['response']
    assert [s['id'] for s in r['sources']] == ['sec1']
    assert deps.lm.compose_answer.call_args.args[2] == decision['facts']
    assert deps.lm.compose_answer.call_args.args[1] == 'uncertain'
