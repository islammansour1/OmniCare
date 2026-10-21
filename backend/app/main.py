"""OmniCare AI — FastAPI application."""
from __future__ import annotations

import logging
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import StreamingResponse
from .session import session_owner, COOKIE
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .observability import configure_logging, get_request_id, log_event, new_request_id, set_request_id
from .providers import provider_summary
from .schemas import ChatRequest, ChatResponse, HealthResponse
from .service import handle_chat
from .voice.route import router as voice_router

logger = logging.getLogger("omnicare.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("starting OmniCare AI in %s mode", settings.resolved_mode)
    from .runtime import get_runtime

    try:
        n = get_runtime().rag.ingest()
        log_event("startup.rag", status="ok", chunks=n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("RAG ingestion failed")
        log_event("startup.rag", status="error", error=type(exc).__name__)
        raise RuntimeError("Hosted policy index initialization failed") from exc
    yield
    logger.info("shutting down OmniCare AI")


app = FastAPI(title="OmniCare AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or new_request_id()
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        mode=settings.resolved_mode,
        providers=provider_summary(),
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, owner: str = Depends(session_owner)) -> ChatResponse:
    if req.user_id != owner:
        raise HTTPException(403, "Session does not own this user ID")
    rid = req.request_id or get_request_id()
    set_request_id(rid)
    log_event("chat.received", user_id=req.user_id, action=req.action)
    resp = handle_chat(req)
    resp.request_id = rid
    return resp


app.include_router(voice_router)


@app.post("/api/v1/session")
def create_session(request: Request, response: Response):
    from .runtime import get_runtime
    origin = request.headers.get('origin')
    if origin and origin not in settings.cors_origin_list and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Origin not allowed')
    db = get_runtime().db
    owner = db.session_owner(request.cookies.get(COOKIE, ''))
    if not owner:
        token, owner = db.issue_session()
        response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=30*86400)
    return {'user_id': owner}


@app.get('/api/v1/conversations')
def conversations(owner: str = Depends(session_owner)):
    from .runtime import get_runtime
    return get_runtime().db.conversations(owner)


@app.post('/api/v1/conversations')
def new_conversation(owner: str = Depends(session_owner)):
    from .runtime import get_runtime
    return get_runtime().db.create_conversation(owner)


@app.get('/api/v1/conversations/{conversation_id}')
def conversation(conversation_id: str, owner: str = Depends(session_owner)):
    from .runtime import get_runtime
    db = get_runtime().db
    scope = db.resolve_scope(owner, conversation_id)
    messages = []
    for m in db.get_messages(scope, limit=1000):
        if m['role'] == 'user':
            messages.append({'id': m['id'], 'role': 'user', 'text': m['content']})
        else:
            payload = m.get('data', {})
            messages.append({'id': m['id'], 'role': 'assistant', **payload})
    return {'messages': messages, 'draft': db.load_draft(scope)}


@app.post('/api/v1/chat/stream')
async def chat_stream(req: ChatRequest, owner: str = Depends(session_owner)):
    from .runtime import get_runtime
    if req.user_id != owner:
        raise HTTPException(403, 'Session does not own this user ID')
    get_runtime().db.resolve_scope(owner, req.conversation_id)
    async def events():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        def progress(label):
            loop.call_soon_threadsafe(queue.put_nowait, {'type': 'progress', 'label': label})
        async def work():
            try:
                result = await asyncio.to_thread(handle_chat, req, progress)
                await queue.put({'type': 'result', 'response': result.model_dump()})
            except Exception:
                logger.exception('stream failed')
                await queue.put({'type': 'error', 'detail': 'Unable to complete this request. Retry.'})
        task = asyncio.create_task(work())
        try:
            yield 'data: ' + json.dumps({'type': 'progress', 'label': 'Processing your request'}) + '\n\n'
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'
                    continue
                yield 'data: ' + json.dumps(event) + '\n\n'
                if event['type'] in {'result', 'error'}:
                    break
        finally:
            # A disconnected client may retry with the same request ID. The worker
            # finishes its atomic result commit; replay returns that same result.
            if not task.done():
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
