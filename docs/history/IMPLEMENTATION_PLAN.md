# OmniCare AI — Implementation Plan

Source of truth for tasks, decisions, progress, blockers, and **actual** test results.

## Status legend
- [ ] not started
- [~] in progress
- [x] done + verified

## Architecture (decided)

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Vite + Tailwind |
| Backend | FastAPI + Pydantic v2 |
| Orchestration | LangGraph (single graph shared by chat + voice) |
| RAG | Hosted embeddings (OpenAI-compatible) + local Chroma (PersistentClient) |
| LLM | Hosted API (Gemini default; OpenAI / Anthropic / openai-compatible optional) |
| State | SQLite (conversation history + claim drafts) |
| Claims | JSON database (`mock_claims.json`) with file lock + atomic write |
| Voice | Browser mic → WebSocket → hosted STT (Deepgram) → LangGraph → hosted TTS |
| Deploy | Docker Compose |
| Tests | pytest + pytest-asyncio + Vitest (frontend) |

## Non-negotiable constraints honored
- **No local inference models** (no Ollama, no local LLM/embeddings/Whisper/TTS).
- Embeddings/LLM/STT/TTS are all hosted and configurable via env.
- Missing credentials are **reported**, never silently swapped for a local model.
- Hosted inference is the only path: a missing key **fails fast** with a clear error at
  startup (no demo fallback). Health reporting is available after successful startup.

## Vertical slices
1. [x] Shared contracts + seed data + plan
2. [x] Backend: config, schemas, claims tools, persistence, RAG, LangGraph agent, chat/health
3. [x] Frontend: chat UX, contextual cards, claim review form, voice hook
4. [x] Voice: WS endpoint + hosted STT/TTS integration
5. [x] Tests: backend (43 pytest) + RAG eval (golden set + thresholds) + frontend (22 Vitest)
6. [x] Docker + docker-compose + .env.example + README + walkthrough

## Decisions log
- Single entry point: `POST /api/v1/chat` (extended with `action`/`draft` for explicit
  confirmation). Voice shares the same LangGraph graph.
- Confirmation is a **structured `action: "confirm_submit"`**, never inferred from LLM prose.
- Structured LLM output uses Pydantic models over function/tool calling; the same schema
  validates the model's returned arguments (intent, policy verdict/evidence, claim fields).
- Claim filing runs an LLM-driven **coverage gate**: excluded, unsupported, and uncertain
  perils are flagged before a draft is presented; only covered/conditional perils proceed.
- Idempotency: deterministic idempotency key = hash(owner, policy, type, amount, description).
  `submit_claim` is file-locked + atomic-write; re-confirm returns the original claim id
  (replay path in `confirm_node`).
- Conversation + draft state in SQLite; the JSON claims store is append-only for new claims.
- Opaque browser sessions enforce conversation and new-claim ownership; the two seed claims are public examples.
- Inference is always hosted. `OMNICARE_MODE` is retained for backward compatibility but
  always resolves to `live`; a missing key fails fast rather than entering a demo.

## Current validation (2026-10-21)
- Backend: 105 tests passed, including ownership, conversation persistence, retry recovery,
  ambiguous coverage, changed-policy ingestion and exact evidence verification.
- Frontend: 27 tests passed; production build passed.
- Earlier audit, before iterative retrieval: 25 cases, 92% verdict accuracy, 94.7% Recall@1,
  100% citation and unsupported handling. Two verdict mismatches remain.
- Separate hosted policy: 8/8 cases passed; semantic claim search: 3/3 passed.
- Gemini: live chat and gemini-embedding-001 smoke requests both returned HTTP 200;
  embeddings returned 3072-dimensional vectors. Full hosted audit results are recorded in docs/PIPELINE_AUDIT.md.
- Docker Compose configuration validated. User will launch rebuilt containers.
- Browser: session startup, mixed flood/property exclusion, new chat, restored history
  and expanded citations verified with isolated sample data.

## Completed reference-review improvements
- [x] Retrieved policy evidence replaces hard-coded answer constants; hosted analysis
  uses validated exact quotes, with clarification for uncertain incidents.
- [x] Hybrid vector/BM25 retrieval; content fingerprints refresh changed policies.
- [x] Evaluation includes mixed exclusions, follow-ups, appraisal boundaries and
  a real hosted-analysis runner (nonzero exit when unavailable or gates fail).
- [x] Owned resumable conversations, full citation/card persistence, fresh contexts.
- [x] SSE progress and request-ID retry recovery without duplicate history.
- [x] Hosted semantic claim search, browser-session ownership, sample-record rules.
- [x] Removed misleading citation confidence percentages.
- [x] Gemini-only environment template; same key automatically configures embeddings.

## Limits
- Browser sessions are prototype identities, not verified policyholder accounts.
- Hosted quote verification establishes provenance but does not prove interpretation
  correctness.
- Streaming sends progress plus a complete card, not model text tokens.
- Claim search ranks at most 20 semantic candidates before model selection.
  Per-call dollar-cost telemetry is not implemented.
- Optional speech providers remain unverified. Hosted policy and claim-search
  checks use small synthetic datasets; see the pipeline audit for results and limits.

## Iterative retrieval follow-up
- [x] Model prepares every initial/follow-up search, with the original text preserved.
- [x] Bounded evidence expansion (three rounds), deduplication and conservative stop.
- [x] Original-message claim check independent of extracted fields; reviewed incident
  rechecked before persistence.
- [x] Four hosted full-workflow regressions passed; see claim_workflow_live.json.

## Coverage response voice
- [x] Connected a shared final writing step for coverage answers and claim checks.
- [x] Calm, specific acknowledgment; concise explanation; no duplicate verdict heading.
- [x] Fixed verdict/source links, unsupported-number rejection, evidence fallback.
- [x] Presentation tests cover routing, preservation of evidence, fallback and invented amounts.

## Customer-service clarification flow
- [x] Short clarification messages without repeated coverage cards or policy recitals.
- [x] Reuse current verified policy passages across clarification replies.
- [x] Two-question ceiling, repeated-question stop and explicit-unknown review state;
  persisted across restarts/retries, reset for a model-identified different incident.
- [x] Carry filing intent through short replies and show the cited claim form when
  resolved; ordinary policy questions keep the answer-only flow.
- [x] Original four-message live replay and offline dialogue/UI regression checks.

## Evidence review and clarification voice
- [x] Review relevant coverage, exclusions and conditions before customer questions.
- [x] Expand retrieval for missing document evidence within the existing budget.
- [x] Connect clarification to an LLM writer with neutral alternatives and brief acknowledgment.
- [x] Test review-before-writing order and incomplete-evidence behavior.

## Useful unresolved answers
- [x] Terminal uncertainty goes through the final LLM writer with verified evidence.
- [x] Preserve relevant coverage terms, exclusions and citations without asking again.
- [x] An uncertain mixed account is not treated as proof of a covered/excluded cause.
