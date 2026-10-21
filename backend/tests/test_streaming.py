"""Streaming final-answer composition: token sink and safety-guard behavior.

The hosted model streams answer tokens to a per-thread sink for the SSE client;
the full-string safety guards (numeric/length) must still apply to the completed
text exactly as they do for the batched path.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent.llm import GeminiLanguageModel, LLMUnavailableError, set_token_sink


def _streaming_model(chunks: list[str]) -> GeminiLanguageModel:
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model.model = "test"
    model._llm_text = Mock()
    model._llm_text.stream.return_value = iter(SimpleNamespace(content=c) for c in chunks)
    return model


def test_compose_answer_streams_tokens_and_returns_full_text():
    model = _streaming_model(["Covered. ", "A pipe burst is covered."])
    sink: list[str] = []
    set_token_sink(sink.append)
    try:
        answer = model.compose_answer("q", "covered", ["A pipe burst is covered."], ["sec1"])
    finally:
        set_token_sink(None)
    assert answer == "Covered. A pipe burst is covered."
    assert sink == ["Covered. ", "A pipe burst is covered."]


def test_compose_answer_guard_still_rejects_new_numbers_when_streaming():
    model = _streaming_model(["Your deductible is $500."])
    set_token_sink(lambda _: None)
    try:
        with pytest.raises(LLMUnavailableError):
            model.compose_answer("q", "covered", ["No numbers here."], ["sec1"])
    finally:
        set_token_sink(None)


def test_compose_clarification_guard_still_applies_when_streaming():
    model = _streaming_model(["Too long"] * 200)
    set_token_sink(lambda _: None)
    try:
        with pytest.raises(LLMUnavailableError):
            model.compose_clarification("q", "unresolved fact", [], [])
    finally:
        set_token_sink(None)


def test_compose_answer_without_sink_uses_batched_call():
    model = GeminiLanguageModel.__new__(GeminiLanguageModel)
    model.model = "test"
    model._llm_text = Mock()
    model._llm_text.invoke.return_value = SimpleNamespace(content="Covered.")
    answer = model.compose_answer("q", "covered", ["Covered."], ["sec1"])
    assert answer == "Covered."
    assert model._llm_text.stream.call_count == 0
