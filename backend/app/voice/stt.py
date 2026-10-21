"""Hosted speech-to-text via Deepgram's streaming WebSocket API."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from ..config import settings

logger = logging.getLogger("omnicare.stt")


class VoiceUnavailableError(Exception):
    pass


class DeepgramSTT:
    """Streams raw PCM16 audio to Deepgram and yields transcript events."""

    def __init__(self) -> None:
        if not settings.deepgram_api_key:
            raise VoiceUnavailableError(
                "Speech recognition unavailable: DEEPGRAM_API_KEY is not configured."
            )
        self.url = (
            "wss://api.deepgram.com/v1/listen"
            f"?model={settings.deepgram_model}"
            "&encoding=linear16&sample_rate=16000&channels=1"
            "&interim_results=true&smart_format=true"
        )
        self.headers = {"Authorization": f"Token {settings.deepgram_api_key}"}

    async def transcribe(
        self, audio_frames: AsyncIterator[bytes]
    ) -> AsyncIterator[dict[str, Any]]:
        """Consume audio frames; yield {"text": str, "final": bool} events."""
        import websockets

        async with websockets.connect(self.url, extra_headers=self.headers) as ws:
            reader = self._reader(ws)
            # Drive audio forwarding concurrently with reading transcripts.
            import asyncio

            async def forward() -> None:
                async for frame in audio_frames:
                    await ws.send(frame)
                # Tell Deepgram the stream is done.
                await ws.send(json.dumps({"type": "CloseStream"}))

            task = asyncio.create_task(forward())
            try:
                async for evt in reader:
                    yield evt
            finally:
                await task

    async def _reader(self, ws) -> AsyncIterator[dict[str, Any]]:
        import websockets

        async for raw in ws:
            if isinstance(raw, bytes):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") != "Results":
                continue
            channel = msg.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                continue
            transcript = alternatives[0].get("transcript", "")
            yield {"text": transcript, "final": bool(msg.get("is_final", False))}
