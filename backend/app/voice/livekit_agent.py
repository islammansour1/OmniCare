"""LiveKit real-time voice agent (the assignment's recommended voice stack).

A LiveKit Agents worker that streams the user's microphone through Deepgram
STT, reuses the shared LangGraph workflow (RAG + coverage + claims) as its
"brain", and speaks the answer back with Deepgram TTS. Voice-activity
detection, turn-taking and interruption handling are provided by LiveKit's
``AgentSession``.

Run (needs LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET / DEEPGRAM_API_KEY):

    python -m app.voice.livekit_agent

The matching frontend gets a signed token from ``POST /api/v1/voice/token`` and
joins room ``voice-<user_id>[-<conversation_id>]``; this worker is dispatched
into that room. The conversation id binds voice turns to the same thread as chat.
"""
from __future__ import annotations

import asyncio
import logging
import os

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    llm,
    utils,
)
from livekit.plugins import deepgram, silero

from ..config import settings
from ..observability import log_event
from ..service import handle_transcript

logger = logging.getLogger("omnicare.voice.agent")

_GREETING = (
    "Hi, I'm OmniCare's assistant. I can answer questions about your policy, "
    "check on a claim, or help you file a new one. How can I help?"
)

server = AgentServer()


def _scope_for(ctx: JobContext) -> tuple[str, str | None]:
    """Recover (user_id, conversation_id) from the room name (see token endpoint).

    Rooms are named ``voice-<user_id>`` or ``voice-<user_id>-<conversation_id>``;
    binding the conversation id makes spoken and typed turns share one thread.
    """
    if ctx.room.name and ctx.room.name.startswith("voice-"):
        rest = ctx.room.name[len("voice-"):]
        user_id, _, conversation_id = rest.partition("-")
        return (user_id or "voice-user"), (conversation_id or None)
    for participant in ctx.room.remote_participants.values():
        return participant.identity, None
    return "voice-user", None


class OmniCareLLM(llm.LLM):
    """LiveKit ``LLM`` adapter that delegates to the OmniCare LangGraph agent."""

    def __init__(self, user_id: str, conversation_id: str | None) -> None:
        super().__init__()
        self._user_id = user_id
        self._conversation_id = conversation_id

    @property
    def model(self) -> str:
        return "omnicare-langgraph"

    @property
    def provider(self) -> str:
        return "omnicare"

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs):
        return _OmniCareStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options or agents.DEFAULT_API_CONNECT_OPTIONS,
        )


class _OmniCareStream(llm.LLMStream):
    async def _run(self) -> None:
        # Extract the latest user utterance; the LangGraph agent keeps its own
        # history in the database, so we only forward the new words.
        text = ""
        for message in reversed(self._chat_ctx.messages()):
            if message.role == "user":
                text = message.text_content or ""
                break

        if not text.strip():
            answer = _GREETING
        else:
            try:
                result = await asyncio.to_thread(
                    handle_transcript, self._llm._user_id, text, self._llm._conversation_id
                )
                answer = result.response
            except Exception:  # noqa: BLE001 — never leave the user without a reply
                logger.exception("voice turn failed")
                answer = "Sorry, I couldn't process that. Could you repeat it?"

        self._event_ch.send_nowait(
            llm.ChatChunk(
                id=utils.shortuuid(),
                delta=llm.ChoiceDelta(role="assistant", content=answer),
            )
        )


@server.rtc_session(agent_name=settings.livekit_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    user_id, conversation_id = _scope_for(ctx)
    log_event("voice.agent_started", user_id=user_id, room=ctx.room.name)

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        llm=OmniCareLLM(user_id=user_id, conversation_id=conversation_id),
        tts=deepgram.TTS(),
    )

    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions=(
                "You are OmniCare's insurance assistant. Answer coverage questions "
                "using only the policy, look up claim statuses, and help file new "
                "claims. Keep spoken answers short and conversational."
            )
        ),
    )

    await session.generate_reply(instructions="Greet the user and offer your help.")


if __name__ == "__main__":
    # The LiveKit Agents SDK reads these from the environment. Point it at the
    # internal server address and the configured credentials.
    os.environ["LIVEKIT_URL"] = settings.livekit_internal_url or settings.livekit_url
    os.environ["LIVEKIT_API_KEY"] = settings.livekit_api_key
    os.environ["LIVEKIT_API_SECRET"] = settings.livekit_api_secret
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(server.run())
