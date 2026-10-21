"""User journeys, ownership boundaries, failure recovery and grounding regressions."""
import json
from unittest.mock import Mock
import pytest
from app.agent.llm import GeminiLanguageModel, PolicyAnalysis, PolicyEvidence


def auth(client, owner):
    token, _ = client.deps.db.issue_session(owner)
    return {'Authorization': 'Bearer ' + token}


def conversation(client, owner):
    return client.post('/api/v1/conversations', headers=auth(client, owner)).json()['id']


def payload(owner='u1', **kw):
    return {'user_id': owner, 'message': 'Does my policy cover burst pipes?', **kw}


def test_no_auth_and_forged_user_are_rejected(client):
    assert client.post('/api/v1/chat', json=payload(), headers={}).status_code == 401
    assert client.post('/api/v1/chat', json=payload('u2'), headers=auth(client, 'u1')).status_code == 403


def test_cookie_session_persists_and_blocks_cross_origin(client):
    first = client.post('/api/v1/session')
    assert 'HttpOnly' in first.headers['set-cookie']
    assert client.post('/api/v1/session').json() == first.json()
    assert client.post('/api/v1/session', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_conversation_restore_preserves_citations_and_new_chat_is_empty(client):
    a, b = conversation(client, 'u1'), conversation(client, 'u1')
    res = client.post('/api/v1/chat', json=payload(conversation_id=a, request_id='r1')).json()
    saved = client.get(f'/api/v1/conversations/{a}', headers=auth(client, 'u1')).json()
    assert saved['messages'][1]['sources'] == res['sources']
    assert saved['messages'][1]['data'] == res['data']
    assert client.get(f'/api/v1/conversations/{b}', headers=auth(client, 'u1')).json()['messages'] == []
    assert client.get(f'/api/v1/conversations/{a}', headers=auth(client, 'u2')).status_code == 404
    assert client.post('/api/v1/chat', json=payload('u2', conversation_id=a)).status_code == 404


def test_retry_replays_without_duplicate_history_and_rejects_changed_body(client):
    req = payload(request_id='same')
    first = client.post('/api/v1/chat', json=req).json()
    assert client.post('/api/v1/chat', json=req).json() == first
    assert len(client.deps.db.get_messages('u1')) == 2
    assert client.post('/api/v1/chat', json={**req, 'message':'different'}).status_code == 409


def test_stream_has_progress_and_one_terminal_result(client):
    r = client.post('/api/v1/chat/stream', json=payload(request_id='stream1'))
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith('data: ')]
    assert events[0]['type'] == 'progress'
    assert sum(e['type'] == 'result' for e in events) == 1
    assert events[-1]['response']['sources']
    assert client.post('/api/v1/chat', json=payload(request_id='stream1')).json() == events[-1]['response']


def test_error_is_retryable_not_cached_or_leaked(client, monkeypatch):
    original = client.deps.lm.analyze_policy
    monkeypatch.setattr(client.deps.lm, 'analyze_policy', Mock(side_effect=RuntimeError('secret internal failure')))
    result = client.post('/api/v1/chat', json=payload(request_id='retry')).json()
    assert result['message_type'] == 'error'
    assert 'secret' not in json.dumps(result)
    assert client.deps.db.get_messages('u1') == []
    monkeypatch.setattr(client.deps.lm, 'analyze_policy', original)
    assert client.post('/api/v1/chat', json=payload(request_id='retry')).json()['message_type'] == 'coverage_answer'


def test_owned_claims_search_and_lookup_do_not_cross_users(client):
    c = client.deps.claims.submit_claim('POL-1', 'Personal Property', 1500, 'Laptop damage', owner_id='u1')
    client.deps.claims.submit_claim('POL-1', 'Personal Property', 1500, 'Laptop damage', owner_id='u2')
    search = client.post('/api/v1/chat', json=payload(message='What happened to my laptop claim?')).json()
    assert search['message_type'] == 'claim_list'
    assert c['claim_id'] in [x['claim_id'] for x in search['data']['claims']]
    assert all(x.get('owner_id', 'u1') == 'u1' for x in search['data']['claims'])
    other = client.post('/api/v1/chat', json=payload('u2', message='Check ' + c['claim_id'])).json()
    assert other['message_type'] == 'clarification'
    assert c['description'] not in json.dumps(other)


def test_conversation_drafts_do_not_leak(client):
    a, b = conversation(client, 'u1'), conversation(client, 'u1')
    client.post('/api/v1/chat', json=payload(message='File a claim for a burst pipe in my kitchen', conversation_id=a))
    for cid, has_draft in [(a, True), (b, False)]:
        stored = client.get(f'/api/v1/conversations/{cid}', headers=auth(client, 'u1')).json()
        assert bool(stored['draft']) == has_draft


def test_policy_change_same_section_count_reindexes(deps, tmp_path):
    path = tmp_path / 'policy.md'
    original = deps.rag.policy_file.read_text()
    path.write_text(original.replace('$25,000', '$18,000'))
    deps.rag.policy_file = path
    deps.rag.ingest()
    path.write_text(original.replace('$25,000', '$12,000'))
    deps.rag.ingest()
    sources = deps.rag.retrieve('burst pipes')
    analysis = deps.lm.analyze_policy('burst pipes', sources, [])
    assert '$12,000' in ' '.join(analysis['facts'])
    assert '$25,000' not in ' '.join(analysis['facts'])
    assert '$18,000' not in ' '.join(analysis['facts'])


def test_followup_uses_prior_incident(client):
    client.post('/api/v1/chat', json=payload())
    reply = client.post('/api/v1/chat', json=payload(message='What is the deductible for that?')).json()
    assert '$500' in reply['response']
    assert reply['sources'][0]['id'] == 'sec1'


@pytest.mark.parametrize('question, verdict', [
    ('My laptop was damaged by a flood', 'excluded'),
    ('I have water damage', 'uncertain'),
    ('My TV got ruined', 'uncertain'),
    ('My ring is worth $2,000', 'covered'),
    ('My ring is worth $2,501', 'conditional'),
])
def test_ambiguous_and_mixed_coverage(deps, question, verdict):
    SOURCES = [
        {"id": "sec1", "section": "Section 1 — Home Water Damage Coverage",
         "text": "Water damage caused by sudden pipe bursts is covered up to $25,000 with a $500 deductible. Gradual leaks or flood damage are strictly excluded."},
        {"id": "sec2", "section": "Section 2 — Personal Property Protection",
         "text": "Electronics, furniture, and jewelry are covered up to $10,000 total. Single items exceeding $2,500 require individual appraisal receipts."},
    ]
    analysis = deps.lm.analyze_policy(question, SOURCES, [])
    assert analysis['verdict'] == verdict
    if verdict == 'uncertain':
        assert analysis['clarification']


def test_live_analysis_rejects_fabricated_evidence():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict="covered",
        evidence=[PolicyEvidence(source_id="sec1", quote="Covered up to $1 million")],
        clarification="",
    ))
    with pytest.raises(RuntimeError, match='Unverified'):
        model.analyze_policy('pipe burst', [{'id':'sec1','text':'Pipe bursts covered up to $12,000.'}], [])


def test_live_analysis_uses_changed_policy_evidence():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    quote = 'Pipe bursts covered up to $12,000.'
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict="covered",
        evidence=[PolicyEvidence(source_id="new-section", quote=quote)],
        clarification="",
    ))
    result = model.analyze_policy('pipe burst', [{'id':'new-section','text':quote}], [])
    assert result['facts'] == [quote]
    assert result['cited_ids'] == ['new-section']


def test_docker_frontend_origin_can_create_session(client):
    assert client.post('/api/v1/session', headers={'Origin': 'http://localhost:8080'}).status_code == 200
