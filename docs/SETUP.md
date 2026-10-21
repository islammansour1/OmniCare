# OmniCare AI — Setup

This guide covers prerequisites, provider configuration, and how to run
OmniCare AI either in Docker or as a local Python/Node development setup.

OmniCare AI is **hosted-only**: chat, policy analysis, and retrieval all call a
hosted LLM and hosted embeddings. There is no offline or rule-based fallback.
If the configured provider's key is missing, the backend fails fast at startup
with a clear error.

---

## 1. Prerequisites

Choose one of two paths:

- **Docker** — Docker Engine + Docker Compose (no local Python or Node needed).
- **Local development** — Python 3.11+ and Node.js 18+.

For any path you also need an API key from a supported hosted provider (see
[Provider summary](#2-provider-summary)).

---

## 2. Provider summary

Inference is hosted-only. The default and simplest provider is **Gemini**:

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-flash-latest
LLM_API_KEY=your-google-ai-studio-key
```

- Chat uses the selected Gemini model.
- Policy search (embeddings) automatically uses `gemini-embedding-001` with the
  **same key** — no separate embedding configuration is required.
- Embeddings are generated remotely and stored in local Chroma. No local
  inference models are used.

Other supported providers (set `LLM_PROVIDER`):

| Provider | Notes |
| --- | --- |
| `openai` | Uses `OPENAI_API_KEY` (or `LLM_API_KEY`) and `OPENAI_BASE_URL`. |
| `anthropic` | Uses `ANTHROPIC_API_KEY`; model via `ANTHROPIC_MODEL`. |
| `openai-compatible` | Requires **both** `LLM_BASE_URL` and `LLM_MODEL` (any OpenAI-compatible endpoint). |

Embeddings can be overridden independently with `EMBEDDING_PROVIDER`,
`EMBEDDING_MODEL`, `EMBEDDING_API_KEY`, and `EMBEDDING_BASE_URL`. Do not mix
keys and endpoints belonging to different providers.

Real-time voice is optional and runs on **LiveKit** with Deepgram for speech:

- **LiveKit** (transport + VAD + turn-taking): `LIVEKIT_URL`,
  `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`. Use LiveKit Cloud (free tier) or a
  self-hosted `livekit-server` (defaults to `ws://localhost:7880`).
- **Deepgram** (STT + TTS): `DEEPGRAM_API_KEY`.

The voice agent worker (`python -m app.voice.livekit_agent`, or the
`voice-agent` Docker service) connects to LiveKit and reuses the same LangGraph
workflow as chat. A Gemini key alone enables text chat and policy search,
**not** the voice pipeline.

---

## 3. Docker quick start

```bash
# Only if you don't already have .env:
cp .env.example .env
# Add your key to .env, then:
docker compose up --build
```

Then open **http://localhost:8080**.

Notes:

- The `.env` at the **project root** is what Docker Compose reads (not
  `backend/.env`).
- **Do not** overwrite an existing `.env` containing your key; `cp` above is
  guarded for the first-time case only.
- Rebuild after **source** changes (`docker compose up --build`); restart/recreate
  after **configuration** changes (`docker compose up -d` recreates the
  container so it re-reads `.env`).
- The frontend is served on port `8080`; the backend API is exposed on `8000`.
- Persistent data (SQLite, Chroma, claims) lives in the `backend_data` volume,
  seeded from the image on first run.

---

## 4. Local development

Backend (FastAPI + LangGraph):

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
# For local development, put your configuration in backend/.env.
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (React + Vite):

```bash
cd frontend
npm ci
npm run dev
```

In local development the backend loads configuration from `backend/.env`
(not the project-root `.env` that Docker uses).

---

## 5. Configuration reference

All settings are read from environment variables (case-insensitive: the
lowercase field names in `backend/app/config.py` map to the uppercase env vars
below). Paths are resolved relative to `backend/` unless absolute.

**Required** means the backend fails fast at startup without it. **Optional**
means a sensible default applies. **Conditional** means it is required only for
a specific provider/feature.

| Env var | Default | Purpose | Required? |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | `auto` | Selects the hosted LLM provider (`auto`, `openai`, `gemini`, `anthropic`, `openai-compatible`). | Optional (must be set when using `LLM_API_KEY`) |
| `LLM_MODEL` | `""` | LLM model id; defaults to `gemini-flash-latest` (Gemini) or `gpt-4o-mini` (others). | Conditional (required for `openai-compatible`) |
| `LLM_API_KEY` | `""` | Generic API key used together with an explicit `LLM_PROVIDER`. | Required in the default Gemini flow (unless a provider-specific key is set) |
| `LLM_BASE_URL` | `""` | Custom LLM endpoint (OpenAI-compatible, or override Gemini/OpenAI default). | Conditional (required for `openai-compatible`) |
| `GEMINI_API_KEY` | `""` | Gemini key when not using `LLM_API_KEY`. | Conditional (required for `gemini`) |
| `OPENAI_API_KEY` | `""` | OpenAI key (also used by `openai-compatible`). | Conditional (required for `openai`) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL. | Optional |
| `ANTHROPIC_API_KEY` | `""` | Anthropic key. | Conditional (required for `anthropic`) |
| `ANTHROPIC_MODEL` | `claude-3-5-haiku-latest` | Anthropic model id. | Optional |
| `EMBEDDING_PROVIDER` | `auto` | Embedding provider (`auto`, `openai`, `gemini`, `openai-compatible`); defaults to match the LLM provider. | Optional |
| `EMBEDDING_MODEL` | `""` | Embedding model; defaults to `gemini-embedding-001` (Gemini) or `text-embedding-3-small` (OpenAI). | Conditional (required for `openai-compatible` embeddings) |
| `EMBEDDING_API_KEY` | `""` | Embedding key; falls back to the LLM/OpenAI/Gemini key when unset. | Optional |
| `EMBEDDING_BASE_URL` | `""` | Embedding endpoint; falls back to the provider default. | Conditional (required for `openai-compatible` embeddings) |
| `DEEPGRAM_API_KEY` | `""` | Deepgram key for voice STT and TTS. | Optional (voice only) |
| `DEEPGRAM_MODEL` | `nova-2` | Deepgram STT model. | Optional (voice only) |
| `LIVEKIT_URL` | `ws://localhost:7880` | LiveKit server URL the browser uses. | Optional (voice only) |
| `LIVEKIT_INTERNAL_URL` | `""` | LiveKit server URL the backend/agent uses (docker); falls back to `LIVEKIT_URL`. | Optional (voice only) |
| `LIVEKIT_API_KEY` | `devkey` | LiveKit API key. | Optional (voice only) |
| `LIVEKIT_API_SECRET` | `secret` | LiveKit API secret. | Optional (voice only) |
| `LIVEKIT_AGENT_NAME` | `omnicare-agent` | Agent name used for dispatch. | Optional (voice only) |
| `RAG_HYBRID_SEARCH` | `true` | Enable hybrid retrieval (vector + BM25/rank fusion); `false` = vector only. | Optional |
| `RAG_TOP_K` | `4` | Number of retrieval candidates. | Optional |
| `RAG_SCORE_THRESHOLD` | `0.05` | Minimum retrieval score threshold. | Optional |
| `CORS_ORIGINS` | (comma-separated localhost list) | Allowed browser origins. | Optional |
| `LOG_LEVEL` | `INFO` | Logging level. | Optional |
| `HOST` | `0.0.0.0` | Server bind host. | Optional |
| `PORT` | `8000` | Server bind port. | Optional |
| `DATABASE_PATH` | `./data/omnicare.db` | SQLite database path (sessions, history, drafts). | Optional |
| `CLAIMS_PATH` | `./data/mock_claims.json` | Claims store JSON path. | Optional |
| `POLICY_PATH` | `../sample_policy.md` | Policy document path. | Optional |
| `CHROMA_PATH` | `./data/chroma` | Chroma vector index directory. | Optional |

> `OMNICARE_MODE` is a deprecated setting kept for backward compatibility; the
> backend is always hosted (`live`). The legacy `demo` mode was removed.

Net effect of the required keys: at least one LLM key matching your
`LLM_PROVIDER` must be present (`LLM_API_KEY`, `GEMINI_API_KEY`,
`OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`); otherwise startup fails.

---

## 6. Health check

After a successful startup, `GET /api/v1/health` reports per-provider
availability:

```bash
curl http://localhost:8080/api/v1/health
```

The response indicates whether the LLM and embedding providers are configured
(and available), so you can confirm both text chat and policy search are ready
before exercising the API.
