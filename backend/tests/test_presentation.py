from unittest.mock import Mock
from app.agent.nodes import compose_coverage_answer, build_coverage_node
from app.agent.llm import GeminiLanguageModel, LLMUnavailableError
import pytest


def test_coverage_uses_presentation_without_changing_verdict_or_sources(deps):
    deps.lm.analyze_policy = Mock(return_value=dict(verdict='excluded', facts=['Exact evidence.'],
                                                   cited_ids=['sec1'], clarification=''))
    deps.lm.compose_answer = Mock(return_value='I am sorry about the damaged floor. This policy excludes that cause.')
    r = build_coverage_node(deps)({'user_id':'presentation','message':'My floor is damaged','history':[]})['result']
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
