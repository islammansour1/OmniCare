from unittest.mock import Mock
from app.agent.nodes import compose_coverage_answer, build_coverage_node
from app.agent.llm import GeminiLanguageModel, LLMUnavailableError
import pytest


def test_coverage_uses_presentation_without_changing_verdict_or_sources(deps):
    deps.lm.analyze_policy = Mock(return_value=dict(verdict='excluded', facts=['Exact evidence.'],
                                                   cited_ids=['sec1'], clarification=''))
    deps.lm.compose_answer = Mock(return_value='I am sorry about the damaged floor. This policy excludes that cause.')
    r = build_coverage_node(deps).invoke({'user_id':'presentation','message':'My floor is damaged','history':[]})['result']
    assert r['response'] == deps.lm.compose_answer.return_value
    assert r['data']['answer'] == r['response']
    assert r['data']['verdict'] == 'excluded'
    assert [s['id'] for s in r['sources']] == ['sec1']
    assert deps.lm.compose_answer.call_args.args[2] == ['Exact evidence.']


def test_presentation_failure_keeps_evidence_and_clarification(deps):
    deps.lm.compose_answer = Mock(side_effect=LLMUnavailableError('unavailable'))
    text = compose_coverage_answer(deps, 'question', dict(verdict='uncertain',facts=['Exact evidence.'],
                            clarification='What caused the damage?'), [])
    assert 'Exact evidence.' in text
    assert text.endswith('What caused the damage?')


def test_presentation_rejects_invented_amount():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._text = Mock(return_value='We will pay $9000.')
    with pytest.raises(LLMUnavailableError):
        model.compose_answer('question','excluded',['Gradual damage is excluded.'],[])


def test_uncertain_assessment_does_not_invent_a_damage_question():
    from app.agent.llm import PolicyAnalysis, PolicyEvidence
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', evidence=[PolicyEvidence(source_id='a', quote='Terms apply.')]))
    result = model.analyze_policy('A policy question', [{'id': 'a', 'text': 'Terms apply.'}], [])
    assert result['clarification'] == ''
    assert result['needs_review'] is True


def test_candidate_policy_match_cannot_authorize_coverage():
    from app.agent.llm import PolicyAnalysis, PolicyEvidence
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='covered', policy_context='unresolved',
        clarification='What happened to the item?',
        evidence=[PolicyEvidence(source_id='a', quote='Covered subject to conditions.')]))
    result = model.analyze_policy('My item is damaged',
        [{'id': 'a', 'text': 'Covered subject to conditions.'}], [])
    assert result['verdict'] == 'uncertain'
    assert result['policy_context'] == 'unresolved'
    assert result['clarification'] == 'What happened to the item?'


@pytest.mark.parametrize('context, verdict', [
    ('established', 'covered'), ('established', 'excluded'),
    ('established', 'conditional'), ('unresolved', 'covered'),
])
def test_coverage_conclusions_still_require_evidence(context, verdict):
    from app.agent.llm import PolicyAnalysis
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict=verdict, policy_context=context, evidence=[]))
    with pytest.raises(LLMUnavailableError, match='Coverage answer missing evidence'):
        model.analyze_policy('An incident', [], [])


@pytest.mark.parametrize('context', ['established', 'general'])
def test_policy_specific_uncertainty_can_clarify_without_asserting_coverage(context):
    from app.agent.llm import PolicyAnalysis
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context=context, evidence=[],
        clarification='Was the condition met?'))
    result = model.analyze_policy('An incident', [], [])
    assert result['verdict'] == 'uncertain'
    assert result['clarification'] == 'Was the condition met?'
    assert result['facts'] == result['cited_ids'] == []


def test_unresolved_uncertainty_without_question_does_not_crash():
    from app.agent.llm import PolicyAnalysis
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context='unresolved', evidence=[], needs_review=True))
    result = model.analyze_policy('I do not know what happened', [], [])
    assert result['verdict'] == 'uncertain'
    assert result['needs_review']
    assert result['facts'] == result['cited_ids'] == []


@pytest.mark.parametrize('policy_text, terms', [
    ('Sudden pipe bursts qualify. Gradual leaks or flood damage do not.',
     ['Sudden pipe bursts', 'Gradual leaks', 'flood damage']),
    ('Mechanical failure is covered; cosmetic wear is excluded.',
     ['Mechanical failure', 'cosmetic wear']),
])
def test_policy_terms_are_inserted_from_source_without_paraphrasing(policy_text, terms):
    import json
    from app.agent.llm import PolicyQuestionWording, set_token_sink
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyQuestionWording(
        before_terms='Did it involve ', between_terms=', ', after_terms=', or something else?'))
    model._text = Mock(side_effect=AssertionError('Do not rewrite the policy terms as prose'))
    protected = [{'source_id': 'policy', 'quote': term} for term in terms]
    emitted = []
    set_token_sink(emitted.append)
    try:
        answer = model.compose_clarification('An incident', 'Clarify the cause',
            [{'id': 'policy', 'text': policy_text}], [], policy_terms=protected)
    finally:
        set_token_sink(None)
    assert answer == 'Did it involve ' + ', '.join(terms) + ', or something else?'
    assert emitted == [answer]
    assert json.loads(model._tool_call.call_args.args[4])['claim_requested'] is False


def test_unverified_clarification_term_is_rejected_before_wording():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock()
    with pytest.raises(LLMUnavailableError, match='Unverified clarification wording terms'):
        model.compose_clarification('An incident', 'Clarify',
            [{'id': 'a', 'text': 'Actual policy term.'}], [],
            policy_terms=[{'source_id': 'a', 'quote': 'Invented policy term'}])
    model._tool_call.assert_not_called()


def test_clarification_term_capitalization_is_restored_from_source():
    from app.agent.llm import PolicyAnalysis, PolicyEvidence
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context='established', evidence=[],
        clarification='Which condition applies?',
        clarification_terms=[PolicyEvidence(source_id='a', quote='mechanical failure')]))
    result = model.analyze_policy('Equipment broke',
        [{'id': 'a', 'text': 'Mechanical failure is covered.'}], [])
    assert result['clarification_terms'] == [{'source_id': 'a', 'quote': 'Mechanical failure'}]


def test_clarification_term_synonyms_are_not_accepted_as_source_quotes():
    from app.agent.llm import PolicyAnalysis, PolicyEvidence
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context='established', evidence=[],
        clarification='Which condition applies?',
        clarification_terms=[PolicyEvidence(source_id='a', quote='electrical breakdown')]))
    with pytest.raises(LLMUnavailableError, match='Unverified clarification term'):
        model.analyze_policy('Equipment broke', [{'id': 'a', 'text': 'Mechanical failure is covered.'}], [])


def test_observation_plan_does_not_force_another_policy_options_list():
    import json
    from app.agent.llm import ClarificationPlan, PolicyAnalysis, PolicyEvidence
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    plan = ClarificationPlan(known_facts=['Equipment was in the garage'],
        missing_fact='What happened at that location', approach='observation',
        purpose='Narrow the incident after the location-only reply')
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='uncertain', policy_context='established',
        evidence=[PolicyEvidence(source_id='a', quote='Mechanical failure is covered.')],
        clarification='What did you notice there?', clarification_plan=plan,
        clarification_terms=[PolicyEvidence(source_id='a', quote='Mechanical failure')]))
    assessment = model.analyze_policy('Garage', [{'id': 'a', 'text': 'Mechanical failure is covered.'}], [])
    assert assessment['clarification_terms'] == []
    assert assessment['clarification_plan']['approach'] == 'observation'
    model._text = Mock(return_value='What did you notice there?')
    result = model.compose_clarification('Garage', assessment['clarification'],
        [{'id': 'a', 'text': 'Mechanical failure is covered.'}], [],
        clarification_plan=assessment['clarification_plan'])
    assert result == 'What did you notice there?'
    sent = json.loads(model._text.call_args.args[1])
    assert sent['clarification_plan']['known_facts'] == ['Equipment was in the garage']
    assert model._tool_call.call_count == 1
