"""Generic pipeline contracts; semantic quality is checked in hosted evaluations."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.agent.llm import (GeminiLanguageModel, ClaimFieldsResult,
                           RetrievalQuery, ClaimSelection, LLMUnavailableError)
from app.rag.chunking import chunk_policy
from app.rag.embeddings import OpenAIEmbedder


def test_plain_text_and_unrelated_markdown_are_ingested():
    assert chunk_policy('An ordinary paragraph.')[0].text == 'An ordinary paragraph.'
    chunks = chunk_policy('# Agreement\nIntroductory terms.\n## Equipment\nTerms A.\n### Exceptions\nTerms B.')
    assert len(chunks) == 3
    assert chunks[-1].section == 'Agreement / Equipment / Exceptions'
    assert all(c.text for c in chunks)


def test_large_sections_are_bounded_and_keep_source_text():
    text = 'Long unchanged source passage. ' * 300
    chunks = chunk_policy('## Any heading\n' + text, max_chars=400, overlap=50)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 and c.text in text for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_claim_type_is_not_limited_to_sample_policy_categories():
    fields = ClaimFieldsResult(claim_type='Event equipment transit damage')
    assert fields.claim_type == 'Event equipment transit damage'


def test_query_rewrite_is_model_driven_even_without_trigger_words():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=RetrievalQuery(query='generator electrical failure coverage limit'))
    assert model.rewrite_query('And the ceiling?', [{'role':'user','content':'A generator failed.'}]) == 'generator electrical failure coverage limit'
    assert model._tool_call.call_count == 1
    model._tool_call.reset_mock()
    model.rewrite_query('Independent question', [])
    assert model._tool_call.call_count == 1


def test_model_cannot_select_unknown_claim():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=ClaimSelection(claim_ids=['invented']))
    with pytest.raises(LLMUnavailableError):
        model.select_claims('some query', [{'claim_id':'actual'}])


def test_claim_search_filters_ownership_before_embedding(deps):
    deps.claims.submit_claim('POL-A','Novel category',100,'visible description',owner_id='a')
    deps.claims.submit_claim('POL-B','Novel category',100,'hidden private description',owner_id='b')
    calls = []
    class SpyEmbedding:
        index_identity = 'spy'
        def embed_texts(self, texts):
            calls.extend(texts)
            return [[1.0, 0.0] for _ in texts]
    results = deps.claims.search('meaningful paraphrase', 'a', embedder=SpyEmbedding())
    assert all(c.get('owner_id') != 'b' for c in results)
    assert 'hidden private description' not in ' '.join(calls)
    assert 'visible description' in ' '.join(calls)


def test_embedding_response_order_and_shape_validation():
    embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
    embedder.model = 'test'
    create = Mock(return_value=SimpleNamespace(data=[
        SimpleNamespace(index=1,embedding=[0.,1.]), SimpleNamespace(index=0,embedding=[1.,0.])]))
    embedder._client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    assert embedder.embed_texts(['first','second']) == [[1.,0.],[0.,1.]]
    create.return_value = SimpleNamespace(data=[
        SimpleNamespace(index=None,embedding=[1.,0.]), SimpleNamespace(index=1,embedding=[0.,1.])])
    assert embedder.embed_texts(['first','second']) == [[1.,0.],[0.,1.]]
    create.return_value = SimpleNamespace(data=[
        SimpleNamespace(index=None,embedding=[1.,0.]), SimpleNamespace(index=None,embedding=[0.,1.])])
    with pytest.raises(RuntimeError, match='ambiguous'):
        embedder.embed_texts(['first','second'])
    create.return_value = SimpleNamespace(data=[SimpleNamespace(index=0,embedding=[float('nan')])])
    with pytest.raises(RuntimeError, match='invalid vectors'):
        embedder.embed_texts(['one'])
    create.return_value = SimpleNamespace(data=[])
    with pytest.raises(RuntimeError, match='missing or duplicate'):
        embedder.embed_texts(['one'])


def test_failed_reindex_keeps_previous_corpus_and_lexical_snapshot(deps, tmp_path, monkeypatch):
    policy = tmp_path/'independent.md'
    policy.write_text('## Alpha\nOriginal source text.')
    deps.rag.policy_file = policy
    deps.rag.ingest()
    original_store = deps.rag.store
    policy.write_text('## Beta\nReplacement text.')
    monkeypatch.setattr(deps.rag.embedder,'embed_texts',Mock(side_effect=RuntimeError('provider down')))
    with pytest.raises(RuntimeError):
        deps.rag.ingest()
    assert deps.rag.store is original_store
    assert deps.rag.get_chunks()[0].text == 'Original source text.'


def test_wrong_tool_name_is_rejected():
    from langchain_core.messages import AIMessage
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model.model = 'test'
    model._llm = Mock()
    model._llm.bind_tools.return_value.invoke.return_value = AIMessage(
        content='', tool_calls=[{'name': 'unexpected', 'args': {'query': 'x'}, 'id': 't1', 'type': 'tool_call'}])
    with pytest.raises(LLMUnavailableError):
        model._tool_call('rewrite_query', RetrievalQuery, 'description', 'system', 'user')


def test_empty_retrieval_can_request_another_search():
    from app.agent.llm import PolicyAnalysis
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model._tool_call = Mock(return_value=PolicyAnalysis(
        verdict='unsupported', evidence=[], search_queries=['broader policy terms']))
    result = model.analyze_policy('original question', [], [])
    assert model._tool_call.called
    assert result['search_queries'] == ['broader policy terms']
