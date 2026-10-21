"""Hosted text-to-speech (OpenAI tts-1 or Deepgram Aura).

No local TTS models. Without speech-provider credentials, synthesis raises a
clear error so the voice path reports unavailable configuration rather than
faking.
"""
from __future__ import annotations

from ..config import settings


class VoiceUnavailableError(Exception):
    pass


def _check_available() -> None:
    if settings.tts_provider == "deepgram":
        if not settings.deepgram_api_key:
            raise VoiceUnavailableError(
                "TTS unavailable: DEEPGRAM_API_KEY is not configured."
            )
    else:
        if not settings.openai_api_key:
            raise VoiceUnavailableError(
                "TTS unavailable: OPENAI_API_KEY is not configured."
            )


def synthesize(text: str) -> bytes:
    _check_available()
    if settings.tts_provider == "deepgram":
        return _deepgram_tts(text)
    return _openai_tts(text)


def _openai_tts(text: str) -> bytes:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openai_api_key, base_url=settings.openai_base_url
    )
    resp = client.audio.speech.create(
        model=settings.tts_model,
        voice=settings.tts_voice,
        input=text,
    )
    return resp.content


def _deepgram_tts(text: str) -> bytes:
    import httpx

    url = "https://api.deepgram.com/v1/speak"
    params = {"model": "aura-2-echo"} if settings.tts_model == "tts-1" else {"model": settings.tts_model}
    resp = httpx.post(
        url,
        params=params,
        headers={
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content
