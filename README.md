# Contract Risk Radar

A portfolio SaaS demo for English and German residential rental contracts. Upload a PDF, follow background processing, and review original-language evidence, deterministic rule scores, a separate AI assessment, and supported dates. Explanations remain in English.

**Contract analysis demo. Not legal advice.** Bundled samples and evaluation contracts are synthetic. Real uploads require explicit development configuration and upload/transmission consent. Contract text is sent to your configured Claude or Gemini API account. German support does not claim accuracy under German law.

## Start with Docker Compose

Requirements: Docker with Compose v2 and a provider API key.

```sh
cp .env.example .env
# Edit .env: set LLM_MODEL and ANTHROPIC_API_KEY or GEMINI_API_KEY.
docker compose up --build
```

Open http://localhost:5173, create an account, and select a sample or upload an English or German rental PDF with upload consent. FastAPI docs are at http://localhost:8000/docs.

Set `LLM_PROVIDER=claude` or `gemini` and an exact structured-output-capable model identifier. No model is guessed and providers never switch silently. Without a configured model/key, uploads fail readably and can be retried after configuration is corrected. Recreate the worker with `docker compose up -d --force-recreate worker` after editing its environment. Both keys are needed only for provider comparison.

For a multi-workspace Claude API key, also set `ANTHROPIC_WORKSPACE_ID` to the workspace identifier from Claude Console. The provider sends it as the `anthropic-workspace-id` header. A key scoped to a single workspace does not need this setting. This selects the provider's billing/access context; it does not add application workspaces or change document ownership.

Compose starts PostgreSQL, applies queue schema migrations and Alembic, then starts API, worker, and Vite. PDF bytes and Procrastinate jobs live in the same PostgreSQL database. The API and worker use the same Python image. Source mounts support local editing. PostgreSQL persists in a named volume; `docker compose down` keeps it.

## Architecture

```mermaid
flowchart LR
  UI[React: upload and polling] --> API[FastAPI: auth and validation]
  API -->|One transaction: PDF + document + job| DB[(PostgreSQL)]
  DB --> Worker[Procrastinate worker]
  Worker --> PDF[Extract text]
  PDF --> LLM[Claude or Gemini structured extraction]
  LLM --> Evidence[Exact quote verification]
  Evidence --> Rules[Deterministic scoring and dates]
  Rules --> AIReview[Additional AI review + exact verification]
  AIReview -->|Atomic results + completed status| DB
  API --> UI
```

Public routes `/`, `/login`, and `/register` are separate from authenticated `/app` routes. JWT cookies last one hour, survive reloads, and are HttpOnly and SameSite=Lax. Hosted environments enable Secure cookies and require a new secret. Mutations require an allowed Origin header. Example CLI requests therefore need `Origin: http://localhost:5173` and a cookie jar.

Ownership is `documents.user_id`; another user's document, result, retry, and file return 404. Document lists and status do not load PDF bytes or full extracted text. Zustand stores temporary selection/UI state; TanStack Query owns server data and polls processing status every two seconds.

The worker makes one facts request, seven category requests, then one additional AI review request: nine bounded requests, with at most two in flight per job. All must succeed before results are published. Extraction schemas have required nullable fields, a fixed category-discriminated union, and forbidden extras. Both providers use native structured output and application validation. Quotes are normalized identically and checked as exact substrings. Verified canonical fields alone feed calculations. All LLM content is treated as untrusted data and rendered as escaped text.

“Rule-based risk” (`overall_score`) is the highest verified, scorable clause score. “Additional AI assessment” (`ai_overall_score`) is the highest verified model score for conditions outside those rules. Scores are never combined; no scorable evidence means no score. Unverified findings remain visible with warnings. Missing categories are “Not found.” See [RISK_RULES.md](RISK_RULES.md) for all thresholds and limitations.

Limits: 10 MiB, 30 pages, 80,000 extracted characters. Encrypted and invalid PDFs are rejected during upload; PDFs with no text layer fail with a clear worker error. Partially unreadable pages are flagged. No OCR or silent truncation.

Provider network/429/5xx errors get two bounded retries. Other invalid, refused, or truncated outputs fail the whole analysis. Manual retry resets the run identifier atomically and is serialized by a row lock. A per-document queue lock prevents overlapping jobs; stale deliveries cannot save over newer runs. Worker heartbeats support two bounded recovery attempts for stalled jobs, then a readable retryable failure. Graceful interruption also produces a retryable failure; periodic recovery reconciles terminal queue jobs whose application status was not saved.

## Run without Docker

Requirements: Python 3.12+, uv, Node 22.18+, and a local PostgreSQL database. Configure `DATABASE_URL` for your database; `.env` is read from the current directory.

```sh
uv sync --project backend --frozen
cd backend
set -a; . ../.env; set +a
uv run python -m scripts.migrate
uv run uvicorn app.main:app --reload
```

In another terminal, from `backend/` with the same environment, run `uv run python -m app.jobs.worker`. In `frontend/`, run `npm ci` then `npm run dev`.

API keys stay in `.env`, which is ignored. Environment examples contain only a development secret. Do not log contract text, provider responses, credentials, or JWTs. Stage logs include document/run IDs, durations, error codes, and provider/model identifiers.

## Verify

```sh
cd backend
uv run pytest -q
uv run ruff check app tests scripts ../evals ../scripts
```

Unit/API tests can use SQLite as a test fixture. Queue, locking, and PostgreSQL transaction tests require an **isolated database ending in `_test`**; tests truncate this app's tables there.

```sh
export DATABASE_URL=postgresql+psycopg://radar:radar@localhost:5432/radar_test
export TEST_DATABASE_URL="$DATABASE_URL"
uv run python -m scripts.migrate
uv run pytest -q
uv run alembic check
```

```sh
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Browser tests exercise the UI against explicit test-only HTTP fixtures, including failure/retry and evidence gaps; backend integration tests separately exercise the real database and queue with mocked LLM responses. No application mock provider exists. CI runs both, checks schema drift, and verifies OpenAPI/client regeneration.

## Generated API client

```sh
cd backend
uv run python -m scripts.export_openapi
cd ../frontend
npm run generate
```

Commit `backend/openapi.json` and `frontend/src/api/generated/` together. Never hand-edit generated files. The generator is pinned, and generated-code drift fails CI.

## Separate evaluation

Twenty-one held-out synthetic contracts have explicitly authored category/quote ground truth (the original twelve plus six German and three English cases), including repeated categories, benign clauses, business-day terms, missing facts, and prompt injection content. They are separate from the three app samples. The runner uses the application extraction/verification pipeline without importing database or API code.

From the repository root:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m evals.run --validate
PYTHONPATH=backend backend/.venv/bin/python -m evals.run --provider both \
  --claude-model YOUR_CLAUDE_MODEL --gemini-model YOUR_GEMINI_MODEL
```

Supply credentials through environment variables or a root `.env`. Live runs make nine extraction/review requests per contract plus any transient retries: 378 initial requests for both providers. Reports go to `evals/reports/comparison.json`; none are fabricated or checked in as measured model performance.

Predictions must verify before matching. Match exact normalized evidence spans to gold one-to-one, independent of category, with IoU ≥ 0.5. Report clause recall, category accuracy among matched clauses, quote verification rate across returned quotes, per-category counts, unmatched predictions, failures, latency, and token usage. Failed contracts stay in the recall denominator. The nine new contracts also contain manually authored additional-AI evidence and subjective practical-impact references. AI evidence recall, category attribution, verification, unmatched predictions, and reference score differences are reported separately. Older contracts have no AI ground truth and are excluded from that comparison. These metrics measure synthetic extraction, not legal accuracy.

Authoring sources are `samples/contracts.json` and `evals/contracts.json`. To regenerate PDFs and gold offsets after reviewing a source change, run `backend/.venv/bin/python scripts/build_contracts.py`. Evaluation categories/quotes are authored manually; the builder computes only normalized offsets. Never tune prompts or rules against the held-out evaluation set.

## Migrations and scope

The migration command applies the bundled Procrastinate schema on first startup, records its included migration names, applies new bundled SQL migrations on upgrades, then runs Alembic. Stop API and worker during upgrades. It refuses to adopt an existing unmanaged queue schema automatically.

This MVP supports residential rentals and user ownership only. It excludes agents, RAG, vector stores, Redis, S3, OCR, other contract types, organizations/workspaces, PDF editing, rewriting, chat, and reminders. `FileStorage` is the boundary for a future storage adapter; an S3 implementation would need its own consistency strategy.

## Real uploads in local development

The default `.env.example` has `ALLOW_REAL_DOCUMENTS=false`. To test an authorized real document locally, set both `ENVIRONMENT=development` and `ALLOW_REAL_DOCUMENTS=true`, then recreate API and worker. The flag is ineffective outside development. `GET /api/capabilities` exposes supported languages and whether real uploads are enabled. Choose **Real contract (local development)** and confirm authorization and transmission consent before uploading. Synthetic examples must contain no real personal information. Consent is an attestation, not proof of provenance.

Uploads use multipart `file`, `document_kind` (`synthetic` or `real`), and `analysis_consent_confirmed`. The obsolete synthetic-English confirmation field is no longer accepted as a substitute. Unsupported/unknown languages and non-residential documents fail with English messages. Canonical amounts and dates use decimals/ISO dates; ambiguous rent components remain unknown.

## Interactive evidence viewer

Results show the source PDF on the left and findings on the right, with independent scrolling. On mobile, use PDF / Findings tabs. Only verified findings scoring 2–5 are highlighted. Select a highlight to select and focus its finding; use **View in PDF** to navigate to the first exact occurrence. Shared passages offer a finding chooser. Repeated, multiline, and cross-page evidence is mapped from PDF.js text with the same normalization as the backend. Missing PDF locations and preview failures preserve results and the source download.

React-PDF 11.0.0 uses an application-served worker, CMaps, fonts, and Wasm resources. `predev` / `prebuild` copy assets from the pinned PDF.js dependency; no CDN is used. PDF bytes stay in memory and the source file is not modified. Pages intersecting the viewer and their neighbors render canvases. Annotation actions are disabled; document and model text is rendered as escaped text. Verification establishes that a quote exists, not that its interpretation is correct.

## Upgrade to hybrid analysis

Stop API and worker before applying the additive migration. Existing documents become synthetic, existing analysis language is English, and AI review is **not run**. Existing completed analyses and PDF bytes remain available. Re-upload a document to request the new AI assessment; no historical analysis is rewritten automatically.

```sh
docker compose stop api worker frontend
docker compose build api worker migrate frontend
docker compose run --rm migrate
docker compose up -d
```

Prompt/schema versions are 2.0; deterministic rules remain 1.0 and the separate AI rubric is 1.0. Real user PDFs must never enter samples, development fixtures, or the evaluation corpus.
