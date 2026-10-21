"""Evaluation-accounting tests, not synthetic claims of model intelligence.

These fixed responses test the scorer, never masquerade as coverage reasoning.
Hosted quality is measured separately against the unchanged golden dataset.
"""
from types import SimpleNamespace
from eval_runner import evaluate_cases, passes_gate, format_summary, load_golden_set

CASES = [
    {'id':'supported', 'query':'question one', 'expected_verdict':'covered', 'expected_section_id':'a'},
    {'id':'unknown', 'query':'question two', 'expected_verdict':'unsupported', 'expected_section_id':None},
]
SOURCES = [{'id':'a','text':'A source passage.'}]


def test_accounting_and_gate():
    answers = iter([{'verdict':'covered','cited_ids':['a']}, {'verdict':'unsupported','cited_ids':[]}])
    result = evaluate_cases(CASES, lambda q:SOURCES, ['a'], analyzer=lambda *a: next(answers))
    assert result['metrics']['verdict_accuracy'] == 1
    assert passes_gate(result)
    assert '100.0%' in format_summary(result, mode='scorer fixture')


def test_wrong_abstention_does_not_get_citation_credit():
    result = evaluate_cases(CASES[:1], lambda q:SOURCES, ['a'],
                            analyzer=lambda *a: {'verdict':'unsupported','cited_ids':[]})
    assert result['metrics']['citation_validity'] == 0
    assert not passes_gate(result)


def test_failure_counts_once_and_does_not_abort_or_retry():
    calls = []
    def broken(*a):
        calls.append(1)
        raise RuntimeError('provider secret not included in report')
    result = evaluate_cases(CASES, lambda q:SOURCES, ['a'], analyzer=broken)
    assert len(calls) == 2
    assert result['metrics']['errors'] == 2
    assert result['metrics']['verdict_accuracy'] == 0
    assert not passes_gate(result)
    assert 'secret' not in str(result)


def test_extra_valid_evidence_does_not_fail_required_evidence_check():
    result = evaluate_cases(CASES[:1], lambda q:SOURCES, ['a','b'],
        analyzer=lambda *a: {'verdict':'covered','cited_ids':['a','b']})
    assert result['metrics']['citation_validity'] == 1


def test_golden_set_covers_all_outcomes():
    cases = load_golden_set()
    assert len(cases) >= 25
    assert {c['expected_verdict'] for c in cases} == {'covered','excluded','conditional','uncertain','unsupported'}
