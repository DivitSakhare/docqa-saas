# docqa-saas

B2B multi-tenant document Q&A SaaS. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the full backend design and [frontend/README.md](frontend/README.md) for the frontend.

**Status:** Backend and frontend are both built and verified end-to-end against the real
NVIDIA NIM, Pinecone, and Docker stack — 63 automated backend tests passing. Both PDF and
DOCX upload are fully supported; nothing is left from the original plan except live
deployment.

Backend, in build order:

- Control plane + auth: tenants/users tables, tenant provisioning with a dedicated
  Postgres schema per tenant, signup, login, JWT issuance, refresh-token session
  management (rotation, logout, logout-all).
- Per-tenant resource tables (`documents`, `ingestion_jobs`, `document_chunks`,
  `conversations`, `messages`) and the per-request schema-binding mechanism that scopes
  a session to the caller's own tenant schema.
- PDF/DOCX upload: local disk storage (tenant-scoped path, filename never taken from
  client input), content sniffed for real PDF magic bytes or a genuine DOCX zip entry
  (`word/document.xml`, not just the shared OOXML signature), `documents` +
  `ingestion_jobs` rows created and returned immediately (`202 Accepted`).
- Ingestion worker (Celery, backed by Redis — see below): parses each pending document
  (per-page for PDF, single-page for DOCX — see ARCHITECTURE.md's Key Decisions),
  chunks it, embeds the chunks via NVIDIA NIM, upserts vectors into the tenant's own
  Pinecone namespace, and writes `document_chunks` + flips `documents.status` to
  `ready`. Retries transient failures up to a bounded limit before landing on `failed`
  with a visible error.
- Chat/RAG endpoint with citations, conversation history, and explicit cross-tenant
  isolation tests.
- An admin-only endpoint to add a teammate to an existing tenant (no email invite flow —
  the admin sets the new user's initial password directly).

**Fully verified against the real NVIDIA NIM and Pinecone APIs**, not just mocked — see
the embedding model note below.

## Prerequisites

- Python 3.11+
- Docker (for local Postgres and Redis)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# then set JWT_SECRET_KEY in .env — generate one with:
python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up -d postgres redis
alembic upgrade head
```

## Run

```bash
uvicorn docqa.main:app --reload --app-dir src
```

API docs at `http://localhost:8000/docs`. Endpoints:

- `POST /api/v1/auth/signup` — create a tenant, provision its Postgres schema, create the
  first admin user.
- `POST /api/v1/auth/login` — email + password → access + refresh token pair.
- `POST /api/v1/auth/refresh` — exchange a refresh token for a new pair (single-use;
  rotates the refresh token).
- `POST /api/v1/auth/logout` — revoke one refresh token (ends one session).
- `POST /api/v1/auth/logout-all` — revoke every refresh token for the caller.
- `GET /api/v1/auth/me` — resolve the current user from a bearer token.
- `POST /api/v1/documents` — upload a PDF or DOCX file (multipart). Saves it to local
  disk under `STORAGE_ROOT`, creates a `documents` row (`status=pending`) and an
  `ingestion_jobs` row, and returns immediately.
- `GET /api/v1/documents` — list documents in the caller's own tenant schema.
- `POST /api/v1/chat` — ask a question; grounded in the caller's tenant documents, with
  citations. Pass a prior response's `conversation_id` to continue that conversation.
- `GET /api/v1/conversations` / `GET /api/v1/conversations/{id}` — list/open the
  caller's own conversations.
- `GET /api/v1/team/members` — list every user in the caller's tenant.
- `POST /api/v1/team/members` — add a user to the caller's tenant (admin-only, 403
  otherwise).
- `GET /health`

## Ingestion worker

A Celery worker, not a thread inside the API server. Documents are ingested
event-driven: uploading one enqueues a task immediately (see
[`services/document_upload.py`](src/docqa/services/document_upload.py)) rather than
waiting on any polling loop. Needs `REDIS_URL` (the Celery broker — `docker compose up
-d redis` locally publishes it on `localhost:6379`, matching `postgres`'s own published
port), plus `NVIDIA_API_KEY` and `PINECONE_API_KEY` set in `.env` (get them
at [build.nvidia.com](https://build.nvidia.com) and
[app.pinecone.io](https://app.pinecone.io)) — without the NVIDIA/Pinecone keys, jobs fail
with a clear `NVIDIA_API_KEY is not configured` error and retry up to
`INGESTION_MAX_ATTEMPTS` before landing on `failed`. The API itself needs `REDIS_URL` too
(to enqueue), but not the NVIDIA/Pinecone keys.

```bash
celery -A docqa.celery_app worker --loglevel=info
```

A worker crashing mid-task gets that exact task redelivered to another worker
automatically (`task_acks_late` + `task_reject_on_worker_lost` — see
[`celery_app.py`](src/docqa/celery_app.py)); `_process_job`'s own idempotency (clears
partial chunks before reprocessing) is what makes redelivery safe to just re-run. As a
defensive backstop, the worker also resets any job stuck at `processing` back to
`pending` and re-dispatches it once, right when it finishes booting — see
[`services/ingestion.py`](src/docqa/services/ingestion.py)`::reclaim_stuck_jobs`.

**Embedding model note:** `EMBEDDING_MODEL` defaults to `nvidia/llama-nemotron-embed-vl-1b-v2`
(2048-dim), not the newer `nvidia/nemotron-3-embed-1b` the architecture doc's research
originally pointed at — that model, despite being listed as NVIDIA's current free
text-embedding endpoint, hung and timed out on every call during testing (reproduced via
a raw HTTP request with no LangChain involved, and independently via NVIDIA's own
official playground for that model — so this isn't specific to this codebase). Revisit
if NVIDIA fixes it, since it's ostensibly the more capable of the two.

## Frontend

A Next.js app in [`frontend/`](frontend) — the only client, and it never calls this API
directly from the browser. Its own Route Handlers act as a backend-for-frontend: they
hold the access/refresh tokens in httpOnly cookies and proxy every call to this API. See
[`frontend/README.md`](frontend/README.md) for the full design and how to run it
(short version: `npm install && npm run dev` inside `frontend/`, with `API_BASE_URL`
pointed at this API in `frontend/.env.local`).

## Tests

Tests run against a real Postgres database (`docqa_test`, created automatically on the
same instance as dev) — no mocks on the DB layer, since correct schema-per-tenant
behavior is the thing actually worth verifying here.

```bash
docker compose up -d postgres
pytest
```

## Lint / format

```bash
ruff check src tests
ruff format src tests
```

## Migrations

Alembic manages the `public` (control-plane) schema only — `tenants`, `users`.

```bash
alembic revision --autogenerate -m "message"
alembic upgrade head
```

Per-tenant tables (`documents`, `ingestion_jobs`, `document_chunks`) are declared against
a separate `TenantBase` (its own SQLAlchemy metadata, see
[`db/tenant_base.py`](src/docqa/db/tenant_base.py)) and are **not** Alembic-managed.
`provision_tenant` creates them directly in a new tenant's schema via
`TenantBase.metadata.create_all`, using SQLAlchemy's `schema_translate_map` to target the
right schema. This is the known gap in the current design: there's no mechanism yet to
apply a schema change to tenants that already exist, or to backfill tenants provisioned
before a given tenant-table change. That needs a small script looping over existing
tenant schemas — not built yet, tracked as a follow-up rather than blocking.
