"""Provider selection and actual SDK request routing, without network calls."""
import json

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    import os
    for name in list(os.environ):
        if name.startswith(('LLM_', 'EMBEDDING_', 'OPENAI_', 'ANTHROPIC_', 'GEMINI_', 'OMNICARE_')):
            monkeypatch.delenv(name)


def config(**kwargs):
    return Settings(_env_file=None, **kwargs)


def test_gemini_three_variable_environment(monkeypatch):
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('LLM_MODEL', 'gemini-test-model')
    monkeypatch.setenv('LLM_API_KEY', 'google-test-key')
    s = config(openai_api_key='unrelated-key')
    assert s.resolved_mode == 'live'
    assert s.llm_api_key_resolved == s.embedding_api_key_resolved == 'google-test-key'
    assert s.embedding_model_resolved == 'gemini-embedding-001'
    assert s.llm_base_url_resolved == s.embedding_base_url_resolved
    assert 'googleapis.com' in s.llm_base_url_resolved


@pytest.mark.parametrize('kwargs,provider', [
    ({'openai_api_key': 'legacy'}, 'openai'),
    ({'anthropic_api_key': 'legacy'}, 'anthropic'),
    ({'gemini_api_key': 'legacy'}, 'gemini'),
    ({'llm_provider': 'anthropic', 'llm_api_key': 'new'}, 'anthropic'),
    ({'llm_provider': 'openai-compatible', 'llm_api_key': 'new',
      'llm_model': 'custom', 'llm_base_url': 'https://example.com/v1'}, 'openai-compatible'),
])
def test_provider_selection(kwargs, provider):
    s = config(**kwargs)
    assert s.llm_provider_resolved == provider
    assert s.has_llm


def test_missing_selected_key_does_not_use_another_provider():
    with pytest.raises(ValidationError, match='requires LLM_API_KEY'):
        config(llm_provider='gemini', openai_api_key='wrong-provider')
    with pytest.raises(ValidationError):
        config(llm_provider='misspelled')


def test_separate_embedding_provider():
    s = config(llm_provider='gemini', llm_api_key='google-key',
               embedding_provider='openai', embedding_api_key='embedding-key')
    assert s.embedding_api_key_resolved == 'embedding-key'
    assert s.embedding_base_url_resolved == 'https://api.openai.com/v1'
    assert s.embedding_model_resolved == 'text-embedding-3-small'


def test_gemini_chat_wires_gemini_model(monkeypatch):
    from app.agent import llm
    from app import providers
    s = config(llm_provider='gemini', llm_model='gemini-test', llm_api_key='google-key')
    for module in (llm, providers):
        monkeypatch.setattr(module, 'settings', s)
    model = llm.get_language_model()
    assert model.model == 'gemini-test'
    assert model._llm.model == 'gemini-test'
    key = model._llm.google_api_key
    assert (key.get_secret_value() if hasattr(key, 'get_secret_value') else key) == 'google-key'
    assert providers.provider_summary()['llm'] == 'gemini'


def test_gemini_embeddings_wire_requests(monkeypatch):
    from app.rag import embeddings
    from app import providers
    s = config(llm_provider='gemini', llm_model='gemini-test', llm_api_key='google-key')
    for module in (embeddings, providers):
        monkeypatch.setattr(module, 'settings', s)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'data': [{'index': 0, 'embedding': [0.1, 0.2]}],
                                       'model': 'gemini-embedding-001', 'object': 'list'})

    import openai
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: OpenAI(
        **kw, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    embedder = embeddings.get_embedder()
    assert embedder.embed_texts(['policy']) == [[0.1, 0.2]]
    assert providers.provider_summary()['embeddings'] == 'gemini'
    assert all(r.url.host == 'generativelanguage.googleapis.com' for r in requests)
    assert all(r.headers['authorization'] == 'Bearer google-key' for r in requests)
    assert json.loads(requests[0].content)['model'] == 'gemini-embedding-001'
    assert json.loads(requests[0].content)['encoding_format'] == 'float'


def test_missing_key_fails_fast(monkeypatch):
    from app.agent import llm as llm_module
    from app.rag import embeddings as embeddings_module
    from app import providers
    s = config()
    for module in (llm_module, embeddings_module, providers):
        monkeypatch.setattr(module, 'settings', s)
    with pytest.raises(RuntimeError):
        llm_module.get_language_model()
    with pytest.raises(RuntimeError):
        embeddings_module.get_embedder()


def test_switching_embeddings_keeps_indexes_separate(tmp_path):
    from fakes import FakeEmbedder
    from app.rag.vectorstore import VectorStore
    from app.rag.chunking import Chunk
    first = FakeEmbedder()
    first.index_identity = 'provider-a/model-a'
    second = FakeEmbedder()
    second.index_identity = 'provider-b/model-b'
    a = VectorStore(tmp_path, first)
    a.add_chunks([Chunk(id='sec1', section='Test', text='policy')])
    b = VectorStore(tmp_path, second)
    assert b.count() == 0
    assert a.count() == 1
    b.reset()
    assert a.count() == 1
    assert VectorStore(tmp_path, first).count() == 1
