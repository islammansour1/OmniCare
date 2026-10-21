"""Shared, serialized turn handling with retry-safe results and persisted cards."""
from __future__ import annotations
import hashlib
import logging
import time
from filelock import FileLock
from .agent import run_agent
from .agent.llm import set_token_sink
from .config import settings
from .observability import get_request_id, log_event
from .schemas import ChatRequest, ChatResponse

logger = logging.getLogger('omnicare.service')


def handle_chat(req: ChatRequest, on_progress=None, on_token=None, interactive: bool = True) -> ChatResponse:
    from .runtime import get_runtime
    rt = get_runtime()
    scope = rt.db.resolve_scope(req.user_id, req.conversation_id)
    lock_path = rt.db.path.parent / ('turn-' + hashlib.sha256(scope.encode()).hexdigest()[:24] + '.lock')
    body_hash = hashlib.sha256(req.model_dump_json(exclude={'request_id'}).encode()).hexdigest()
    start = time.perf_counter()
    with FileLock(str(lock_path), timeout=60):
        if req.request_id:
            cached = rt.db.cached_turn(scope, req.request_id, body_hash)
            if cached:
                return ChatResponse(**cached)
        # Interactive turns run against the persistent checkpointer and resume a
        # pending confirmation interrupt when the client supplies a decision.
        checkpointer = thread_id = resume = None
        if interactive:
            from .agent.checkpoint import build_checkpointer
            checkpointer = build_checkpointer()
            thread_id = scope
            if req.action in ("confirm_submit", "cancel_submit"):
                resume = {"action": req.action,
                          "draft": req.draft.model_dump(exclude_none=True) if req.draft else {}}
        # Stream final-answer tokens to the caller (per-thread; cleared in finally).
        if on_token:
            set_token_sink(on_token)
        try:
            result = run_agent(
                user_id=scope, owner_id=req.user_id, message=req.message, action=req.action,
                draft_input=req.draft.model_dump(exclude_none=True) if req.draft else None,
                history=rt.db.get_history(scope), deps=rt, on_progress=on_progress,
                checkpointer=checkpointer, thread_id=thread_id, resume=resume, interactive=interactive)
        except Exception:
            logger.exception('agent turn failed')
            # Errors are not cached/persisted so the same request can be retried.
            return ChatResponse(response='I could not complete that request. Please retry.',
                message_type='error', data={'code': 'processing_failed', 'detail': 'Please retry.'},
                request_id=req.request_id or get_request_id(), mode=settings.resolved_mode)
        finally:
            if on_token:
                set_token_sink(None)
        response = ChatResponse(**result, request_id=req.request_id or get_request_id(), mode=settings.resolved_mode)
        rt.db.record_turn(scope, req.message, response.model_dump(), req.request_id, body_hash)
        rt.db.update_conversation_activity(req.user_id, req.conversation_id, req.message)
    log_event('turn.completed', message_type=response.message_type,
              elapsed_ms=round((time.perf_counter()-start)*1000))
    return response


def handle_transcript(user_id: str, transcript: str, conversation_id: str | None = None) -> ChatResponse:
    # Voice turns are stateless: no confirmation interrupts (a spoken turn has
    # no action flag to resume with).
    return handle_chat(
        ChatRequest(user_id=user_id, message=transcript, conversation_id=conversation_id),
        interactive=False,
    )
