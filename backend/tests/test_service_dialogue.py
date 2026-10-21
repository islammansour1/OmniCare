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


def test_short_questions_refresh_evidence_and_stop_after_two_even_after_restart(deps):
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
    assert deps.rag.retrieve.call_count > calls
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
    assert r['data']['policy_dialogue']['questions'] == 0


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


def test_clarification_wording_failure_preserves_evidence_based_question(deps):
    from app.agent.llm import LLMUnavailableError
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis(question='Where was the item stored?'))
    deps.lm.compose_clarification = Mock(side_effect=LLMUnavailableError('unavailable'))
    response = turn(deps, 'An incident')
    assert response['message_type'] == 'clarification'
    assert response['response'] == 'Where was the item stored?'


def test_unestablished_policy_category_guides_question_but_not_wording(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', 'damage to floor'))
    deps.lm.analyze_policy = Mock(return_value=analysis(
        question='What happened to the floor?', policy_context='unresolved'))
    deps.lm.compose_clarification = Mock(return_value='What happened to the floor?')
    response = turn(deps, 'My floor is all messed up and I need it fixed asap')
    assert response['message_type'] == 'clarification'
    assert response['sources'] == []
    assert deps.lm.compose_clarification.call_args.args[2] == []
    assert response['data']['policy_dialogue']['evidence']


def test_unestablished_category_not_explained_when_questioning_stops(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', 'damage to floor'))
    deps.lm.analyze_policy = Mock(return_value=analysis(
        question='', needs_review=True, policy_context='unresolved'))
    deps.lm.compose_answer = Mock(return_value='The cause of the damage remains unclear.')
    response = turn(deps, 'I do not know what happened')
    assert response['message_type'] == 'coverage_answer'
    assert response['sources'] == []
    assert deps.lm.compose_answer.call_args.args[2:] == ([], [])


def test_real_analysis_validator_allows_uncited_clarification_through_graph(deps):
    from app.agent.llm import GeminiLanguageModel, PolicyAnalysis
    from types import SimpleNamespace
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context='unresolved', evidence=[],
        clarification='What happened to the floor?'))
    deps.lm.classify_intent = Mock(return_value=('coverage', 'floor damage'))
    deps.lm.analyze_policy = model.analyze_policy
    deps.lm.review_evidence = Mock(return_value=SimpleNamespace(sufficient=True, search_queries=[]))
    deps.lm.compose_clarification = Mock(return_value='What happened to the floor?')
    response = turn(deps, 'My floor is all messed up and I need it fixed asap')
    assert response['message_type'] == 'clarification'
    assert response['response'] == 'What happened to the floor?'
    assert response['sources'] == []
    deps.lm.review_evidence.assert_called_once()
    assert deps.lm.compose_clarification.call_args.args[2] == []


def test_useful_partial_answers_can_continue_past_two_questions_after_restart(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(side_effect=[
        analysis(question='Where did it start?'),
        analysis(question='What did you notice there?', clarification_progress=True),
        analysis(question='When did you first notice that?', clarification_progress=True),
        analysis('covered'),
    ])
    assert turn(deps, 'Water damaged my floor')['message_type'] == 'clarification'
    second = turn(deps, 'Kitchen')
    assert second['data']['policy_dialogue']['stalled_turns'] == 0
    deps.db = Database(deps.db.path)
    third = turn(deps, 'Water was coming from below the sink')
    assert third['message_type'] == 'clarification'
    assert third['data']['policy_dialogue']['questions'] == 3
    assert third['data']['policy_dialogue']['stalled_turns'] == 0
    fourth = turn(deps, 'The pipe split while I was there')
    assert fourth['message_type'] == 'coverage_answer'
    history = deps.lm.analyze_policy.call_args.args[2]
    assert any(m['content'] == 'Kitchen' for m in history)
    assert any(m['content'] == 'Water was coming from below the sink' for m in history)


def test_repeated_replies_stop_after_progress_and_remain_stopped_on_restart(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(side_effect=[
        analysis(question='Where did it start?'),
        analysis(question='What did you notice there?', clarification_progress=True),
        analysis(question='Can you describe what you saw?'),
        analysis(question='Do you have any more details?'),
        analysis(question='Anything else?'),
    ])
    turn(deps, 'Water damaged my floor')
    turn(deps, 'Kitchen')
    assert turn(deps, 'Kitchen')['message_type'] == 'clarification'
    terminal = turn(deps, 'Kitchen')
    assert terminal['message_type'] == 'coverage_answer'
    assert terminal['data']['policy_dialogue']['stalled_turns'] == 2
    deps.db = Database(deps.db.path)
    assert turn(deps, 'Kitchen')['message_type'] == 'coverage_answer'


def test_known_subject_supplies_only_verified_relevant_terms_to_writer(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', 'water damage'))
    deps.rag.retrieve = Mock(return_value=[
        {'id': 'water', 'section': 'Water', 'text': 'Policy conditions for water.'},
        {'id': 'unrelated', 'section': 'Other subject', 'text': 'Unrelated terms.'},
    ])
    deps.lm.analyze_policy = Mock(return_value={**analysis(
        question='Which documented cause applies?', policy_context='established'),
        'cited_ids': ['water']})
    deps.lm.compose_clarification = Mock(return_value='A question based on the policy terms')
    response = turn(deps, 'Water damaged my floor')
    assert response['message_type'] == 'clarification'
    assert [s['id'] for s in deps.lm.compose_clarification.call_args.args[2]] == ['water']


def test_rewritten_retrieval_assessment_policy_question_and_resolved_followup(deps):
    from app.agent.llm import GeminiLanguageModel, PolicyAnalysis, PolicyEvidence, PolicyQuestionWording
    text = 'Sudden pipe bursts qualify. Gradual leaks or flood damage are excluded.'
    terms = ['Sudden pipe bursts', 'Gradual leaks', 'flood damage']
    stages = []
    def retrieve(query):
        stages.append(('retrieve', query))
        return [{'id': 'water', 'section': 'Water', 'text': text}]
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(side_effect=[
        PolicyAnalysis(verdict='uncertain', policy_context='established',
            evidence=[PolicyEvidence(source_id='water', quote=text)],
            clarification='Which policy cause applies?',
            clarification_terms=[PolicyEvidence(source_id='water', quote=t) for t in terms]),
        PolicyQuestionWording(before_terms='Did it involve ', between_terms=', ', after_terms=', or something else?'),
        PolicyAnalysis(verdict='covered', policy_context='established',
            evidence=[PolicyEvidence(source_id='water', quote='Sudden pipe bursts qualify.')]),
    ])
    deps.lm.classify_intent = Mock(side_effect=[('coverage', 'rewritten water question'),
                                              ('coverage', 'rewritten incident with confirmed cause')])
    deps.lm.analyze_policy = model.analyze_policy
    deps.lm.compose_clarification = model.compose_clarification
    deps.rag.retrieve = retrieve
    first = turn(deps, 'My floor is all flooded up and it ruined my flooring')
    assert first['message_type'] == 'clarification'
    assert first['response'] == 'Did it involve ' + ', '.join(terms) + ', or something else?'
    assert stages == [('retrieve', 'rewritten water question')]
    second = turn(deps, 'The pipe burst while I was there')
    assert second['message_type'] == 'coverage_answer'
    assert second['data']['verdict'] == 'covered'
    assert stages[-1] == ('retrieve', 'rewritten incident with confirmed cause')
    assert model._tool_call.call_args_list[-1].args[0] == 'analyze_policy'


def test_terminal_answer_receives_earlier_incident_facts(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(side_effect=[
        analysis(question='What caused the damage?', policy_context='unresolved'),
        analysis(question='', needs_review=True, policy_context='unresolved'),
    ])
    deps.lm.compose_answer = Mock(return_value='The cause is unknown, so coverage cannot be determined.')
    turn(deps, 'My flooring was damaged')
    result = turn(deps, 'I cannot tell what happened')
    assert result['message_type'] == 'coverage_answer'
    history = deps.lm.compose_answer.call_args.kwargs['history']
    assert any(m['content'] == 'My flooring was damaged' for m in history)


def test_covered_incident_repair_help_offers_claim_and_acceptance_opens_form(deps):
    deps.lm.classify_intent = Mock(side_effect=[('coverage', 'incident'), ('coverage', 'repair help'),
                                              ('claim_submit', 'incident claim')])
    deps.lm.analyze_policy = Mock(side_effect=[
        analysis('covered'), analysis('covered', offer_claim=True),
        analysis('covered', claim_requested=True),
    ])
    deps.lm.extract_claim_fields = Mock(return_value={
        'claim_type': 'Water Damage', 'description': 'Sudden pipe burst damaged flooring'})
    assert turn(deps, 'A pipe broke suddenly and damaged my flooring')['message_type'] == 'coverage_answer'
    offer = turn(deps, 'OK I need to fix the floor then')
    assert offer['message_type'] == 'clarification'
    assert offer['data']['claim_offer'] is True
    assert deps.db.load_draft('dialogue') is None
    draft = turn(deps, 'Yes, please')
    assert draft['message_type'] == 'claim_draft'
    assert draft['data']['confirm_required'] is True
    assert draft['data']['draft']['description'] == 'Sudden pipe burst damaged flooring'
    history = deps.lm.extract_claim_fields.call_args.args[1]
    assert any(m['content'] == 'A pipe broke suddenly and damaged my flooring' for m in history)
    assert deps.claims.list_claims() == []


def test_first_message_offer_claim_explains_coverage_before_offering(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', ''))
    deps.lm.analyze_policy = Mock(return_value=analysis('covered', offer_claim=True))
    deps.lm.compose_answer = Mock(return_value='Sudden pipe bursts are covered up to $25,000.')
    deps.lm.compose_claim_offer = Mock(return_value='Would you like me to start a claim?')
    result = turn(deps, 'A pipe exploded and ruined my floor. Can I get this fixed?')
    assert result['message_type'] == 'coverage_answer'
    assert result['data']['verdict'] == 'covered'
    assert result['data']['claim_offer'] is True
    assert result['response'] == 'Sudden pipe bursts are covered up to $25,000. Would you like me to start a claim?'
    assert result['sources'][0]['id'] == 'sec1'
    assert deps.db.load_draft('dialogue') is None


def test_excluded_incident_cannot_offer_or_draft_a_claim_from_model_flags(deps):
    deps.lm.classify_intent = Mock(return_value=('coverage', 'incident'))
    deps.lm.analyze_policy = Mock(return_value=analysis('excluded', offer_claim=True, claim_requested=True))
    deps.lm.compose_claim_offer = Mock(side_effect=AssertionError('Must not offer an excluded claim'))
    result = turn(deps, 'Help with this incident')
    assert result['message_type'] == 'coverage_answer'
    assert result['data']['verdict'] == 'excluded'
    assert deps.db.load_draft('dialogue') is None
