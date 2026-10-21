"""WebSocket voice endpoint.

Browser streams PCM16/16kHz audio → hosted STT (Deepgram) → the same LangGraph
workflow as chat → hosted TTS → audio back. Interim transcripts are streamed
live so the user sees recognition in real time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..observability import log_event
from ..service import handle_transcript
from .stt import DeepgramSTT, VoiceUnavailableError
from .tts import synthesize

logger = logging.getLogger("omnicare.voice")
router = APIRouter()


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload))


async def _process_utterance(ws: WebSocket, user_id: str, transcript: str, conversation_id: str | None = None) -> None:
    if not transcript.strip():
        await _send(ws, {"type": "state", "state": "idle"})
        return
    await _send(ws, {"type": "state", "state": "processing"})
    try:
        chat_resp = await asyncio.to_thread(handle_transcript, user_id, transcript, conversation_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice turn failed")
        await _send(ws, {"type": "error", "detail": f"Processing failed: {exc}"})
        await _send(ws, {"type": "state", "state": "idle"})
        return

    await _send(
        ws,
        {
            "type": "message",
            "message": {
                "response": chat_resp.response,
                "sources": [s.model_dump() for s in chat_resp.sources],
                "tool_calls": [t.model_dump() for t in chat_resp.tool_calls],
                "message_type": chat_resp.message_type,
                "data": chat_resp.data,
                "mode": chat_resp.mode,
            },
        },
    )
    # Synthesize + stream speech.
    await _send(ws, {"type": "state", "state": "speaking"})
    try:
        audio = synthesize(chat_resp.response)
        await ws.send_bytes(audio)
    except VoiceUnavailableError as exc:
        await _send(ws, {"type": "error", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("TTS failed: %s", exc)
        await _send(ws, {"type": "error", "detail": f"Speech synthesis failed: {exc}"})
    await _send(ws, {"type": "state", "state": "idle"})


@router.websocket("/api/v1/voice")
async def voice_endpoint(websocket: WebSocket, user_id: str, conversation_id: str | None = None) -> None:
    from ..runtime import get_runtime
    from ..session import COOKIE
    from urllib.parse import urlparse
    owner = get_runtime().db.session_owner(websocket.cookies.get(COOKIE, ''))
    origin = websocket.headers.get('origin', '')
    if owner != user_id or (origin not in settings.cors_origin_list and urlparse(origin).netloc != websocket.headers.get('host')):
        await websocket.close(code=1008)
        return
    try:
        get_runtime().db.resolve_scope(owner, conversation_id)
    except Exception:
        await websocket.close(code=1008)
        return
    ws = websocket
    await websocket.accept()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    stt_task: asyncio.Task | None = None
    final_transcript: str = ""

    async def audio_source():
        while True:
            frame = await audio_queue.get()
            if frame is None:
                return
            yield frame

    async def run_stt() -> str:
        stt = DeepgramSTT()
        latest = ""
        async for evt in stt.transcribe(audio_source()):
            if evt["final"]:
                latest = evt["text"]
                await _send(ws, {"type": "transcript", "text": latest, "final": True})
            elif evt["text"].strip():
                await _send(ws, {"type": "transcript", "text": evt["text"], "final": False})
        return latest

    try:
        await _send(ws, {"type": "state", "state": "idle"})
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                log_event("voice.disconnected", user_id=user_id)
                break

            if msg.get("text") is not None:
                data = json.loads(msg["text"])
                typ = data.get("type")
                if typ == "start":
                    final_transcript = ""
                    if settings.deepgram_api_key:
                        stt_task = asyncio.create_task(run_stt())
                        await _send(ws, {"type": "state", "state": "listening"})
                    else:
                        await _send(
                            ws,
                            {
                                "type": "error",
                                "detail": "Voice unavailable: DEEPGRAM_API_KEY is not configured.",
                            },
                        )
                elif typ == "stop":
                    await audio_queue.put(None)
                    if stt_task is not None:
                        final_transcript = await stt_task
                        stt_task = None
                    await _process_utterance(ws, user_id, final_transcript, conversation_id)
                elif typ == "cancel":
                    await audio_queue.put(None)
                    if stt_task is not None:
                        stt_task.cancel()
                        stt_task = None
                    await _send(ws, {"type": "state", "state": "idle"})
            elif msg.get("bytes") is not None:
                if stt_task is not None:
                    await audio_queue.put(msg["bytes"])
    except WebSocketDisconnect:
        log_event("voice.disconnected", user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("voice connection error")
        try:
            await _send(ws, {"type": "error", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        if stt_task is not None:
            stt_task.cancel()
        await audio_queue.put(None)
