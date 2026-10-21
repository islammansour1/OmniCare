"""Real-time voice: hosted STT + shared LangGraph workflow + hosted TTS."""
from .tts import VoiceUnavailableError, synthesize

__all__ = ["VoiceUnavailableError", "synthesize"]
