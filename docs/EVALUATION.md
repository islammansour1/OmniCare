# OmniCare AI — Evaluation

This document describes how to run OmniCare AI's test and evaluation suites,
what each one actually measures, and what they do — and do not — prove.

There are three layers:

1. **Unit/contract tests** — deterministic, offline, no network.
2. **Hosted RAG evaluation** — real hosted embeddings + hosted policy analysis.
3. **Opt-in live checks** — targeted hosted regressions requiring live
   credentials.

---

## 1. Unit / contract tests

Backend (105 tests):

```bash
cd backend
.venv/bin/python -m pytest -q
```

Frontend build + tests (27 tests):

```bash
cd frontend
npm run build
npm run test:run
```

The backend suite (configured via `backend/pytest.ini`) uses deterministic
fakes and runs **without network access**. It verifies orchestration,
validation, ownership, and retry behavior — routing, structured-output schemas,
claim ownership and search, draft confirmation, and idempotent retries.

It does **not** establish semantic quality: these tests check that the wiring
and contracts are correct, not that the model's policy interpretations are
right. Semantic quality is the job of the hosted evaluation below.

---

## 2. Hosted RAG evaluation

```bash
cd backend
.venv/bin/python eval/eval_runner.py
```

This runs each case in `eval/golden_set.json` (25 cases) through the real
`RagPipeline` (hosted embeddings) plus the hosted policy analyzer
(`get_language_model().analyze_policy`). It measures four things:

- **Retrieval Recall@1** — whether `expected_section_id` appears in the top-1
  retrieved sources (supported cases only).
- **Verdict accuracy** — whether the hosted verdict matches `expected_verdict`.
- **Citation validity** — every cited source id exists in the policy chunks and,
  for non-unsupported verdicts, covers the expected required section(s);
  additional valid evidence is allowed.
- **Unsupported-question handling** — unsupported queries must yield verdict
  `unsupported` with zero citations.

Notes:

- It uses an **isolated temp Chroma directory**, so it never touches the
  application's real index under `backend/data`.
- It requires hosted LLM **and** embedding credentials (Gemini, OpenAI, or
  Anthropic); provider errors count as case failures — invalid answers are
  never retried until they happen to pass.
- A Markdown summary is written to `backend/eval/results.md`.
- It **exits nonzero** when the quality gate fails. The gate requires:
  - no provider/validation errors,
  - verdict accuracy ≥ 0.9,
  - citation validity ≥ 0.9,
  - Recall@1 ≥ 0.9,
  - unsupported handling == 100%.

CLI flags:

```text
--policy   Policy Markdown/plain-text file (default: ../sample_policy.md)
--golden   Path to the golden JSON array (default: eval/golden_set.json)
--out      Where to write the Markdown summary (default: eval/results.md)
--top-k    Recall@K window size (default: 1)
```

---

## 3. Generalization evaluation

A separate synthetic policy checks unrelated subjects, limits, and conditions:

```bash
cd backend
.venv/bin/python eval/eval_runner.py --policy eval/generalization_policy.md \
  --golden eval/generalization_cases.json --out eval/generalization_results.md
```

This reuses the same `eval_runner.py` harness against a synthetic policy, to
check that the pipeline does not simply memorize the sample policy.

---

## 4. Opt-in live checks

These require live LLM + embedding credentials (in `backend/.env`). They write
their results next to themselves and exit nonzero on failure.

**Full live evaluation:**

```bash
cd backend
.venv/bin/python eval/eval_live.py
```

A thin wrapper over `eval_runner.py`: it checks credentials, runs the real
hosted evaluation, writes `backend/eval/results_live.md`, and exits nonzero if
credentials are missing (`exit 2`) or the quality gate fails (`exit 1`).

**Targeted regressions** (one line each):

| Script | What it exercises |
| --- | --- |
| `eval/eval_claim_workflow.py` | End-to-end claim workflow verdicts (`excluded`, `claim_draft`, `uncertain`) over four synthetic messages using isolated storage. |
| `eval/eval_clarification_voice.py` | Evidence-review then clarification-composer ordering; asserts a clarification reply and that review precedes composition. |
| `eval/eval_uncertain_details.py` | A two-turn uncertain mixed account ending in a coverage answer with an `uncertain` verdict, sources, no question mark, and the correct limits ($25,000 / $500). |
| `eval/eval_claim_search.py` | Semantic claim search over synthetic records only: candidate retrieval, model selection, and ownership filtering. |
| `eval/eval_service_dialogue.py` | Four-turn customer-service dialogue ending in a `claim_draft` with sources and no more than two clarification turns. |

---

## 5. What these do NOT prove

These evaluations are small and scoped. They do **not** prove universal
reliability:

- Datasets are tiny (25 golden cases plus a handful of synthetic dialogues).
- Model verdicts can vary between runs and provider versions.
- Passing the quality gate is evidence of current behavior on the covered
  cases, not a guarantee of correctness for every policy interpretation,
  numeric answer, or adversarial input.

Treat green results as a regression signal, not as a safety certification.
