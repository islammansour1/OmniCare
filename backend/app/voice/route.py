"""LiveKit voice token endpoint.

The browser asks for a signed LiveKit access token. We create the room,
dispatch the voice agent into it, and return a token so the client can connect
and start streaming its microphone.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from livekit import api as lkapi
from livekit.api import agent_dispatch_service, room_service
from pydantic import BaseModel

from ..config import settings
from ..observability import log_event
from ..runtime import get_runtime
from ..session import session_owner

logger = logging.getLogger("omnicare.voice")

router = APIRouter()


class VoiceTokenResponse(BaseModel):
    url: str
    token: str
    room: str


def _room_name(user_id: str, conversation_id: str | None = None) -> str:
    # "voice-<user_id>" or "voice-<user_id>-<conversation_id>"; the worker parses it back.
    return f"voice-{user_id}" if not conversation_id else f"voice-{user_id}-{conversation_id}"


@router.post("/api/v1/voice/token", response_model=VoiceTokenResponse)
async def voice_token(
    user_id: str,
    conversation_id: str | None = None,
    owner: str = Depends(session_owner),
) -> VoiceTokenResponse:
    if user_id != owner:
        raise HTTPException(403, "Session does not own this user ID")

    # Bind voice to the active conversation so spoken and typed turns share one
    # thread (and validate it actually belongs to the owner).
    if conversation_id:
        get_runtime().db.resolve_scope(owner, conversation_id)

    room = _room_name(user_id, conversation_id)
    internal_url = settings.livekit_internal_url or settings.livekit_url

    async with lkapi.LiveKitAPI(
        internal_url, settings.livekit_api_key, settings.livekit_api_secret
    ) as lk:
        # Create the room (idempotent) so the agent has somewhere to join.
        try:
            await lk.room.create_room(room_service.CreateRoomRequest(name=room))
        except Exception:  # noqa: BLE001 — room already exists
            pass
        # Dispatch the voice agent into the room.
        try:
            await lk.agent_dispatch.create_dispatch(
                agent_dispatch_service.CreateAgentDispatchRequest(
                    agent_name=settings.livekit_agent_name, room=room
                )
            )
        except Exception as exc:  # noqa: BLE001 — non-fatal; the agent may already run
            log_event("voice.dispatch_failed", error=str(exc))

    token = (
        lkapi.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(user_id)
        .with_name(user_id)
        .with_grants(
            lkapi.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True)
        )
        .to_jwt()
    )

    log_event("voice.token_issued", user_id=user_id, room=room)
    return VoiceTokenResponse(url=settings.livekit_url, token=token, room=room)
