# docqa-saas frontend

The client for [docqa-saas](../README.md) — a Next.js (App Router) app. It's the only
client; it never calls the FastAPI backend directly from the browser.

## Stack

- **Next.js 16 (App Router) + TypeScript.**
- **Cookie-based auth via a BFF.** Route Handlers under `app/api/*` proxy every call to
  the FastAPI backend and hold the access/refresh tokens as httpOnly, `Secure` (in
  production), `SameSite=Lax` cookies — browser JS never sees a raw token. This also
  means the backend needs no CORS configuration: the browser only ever talks to this
  app's own origin.
- **Tailwind CSS + shadcn/ui** (Radix-based) for the design system.
- **TanStack Query** for client-side data fetching against this app's own Route
  Handlers (never the backend directly).
- **React Hook Form + Zod** for form validation.
- **next-themes** for light/dark mode.

## Why a BFF instead of a plain SPA

Two tokens live in the backend's session model: a short-lived access token and a
single-use, rotating refresh token (see the root [`ARCHITECTURE.md`](../docs/ARCHITECTURE.md)).
A plain client-side SPA would have to keep both in the browser somehow — memory or
`localStorage` — and could not attach `httpOnly` to either. Route Handlers run
server-side, so they can hold both tokens in real httpOnly cookies instead: this is a
genuine security improvement (no token is ever reachable from browser JS, even under
XSS), not just an architectural preference.

`lib/backend-fetch.ts` is where this lives: it reads the access-token cookie, attaches
it to the backend call, and on a 401 makes exactly one `/auth/refresh` call (rotating
both cookies) before retrying once. Because each request here is its own isolated
serverless invocation, there's no shared in-process state to race the way a client-side
refresh queue would need to guard against — the one edge case worth naming is two
genuinely concurrent requests both hitting an expired access token at once, where the
second's refresh loses because the single-use refresh token was already rotated by the
first. Rare, and it self-heals on the next request or login.

## Structure

```
app/
  page.tsx                 # public landing page
  login/, signup/          # auth pages
  (app)/                   # authenticated route group — layout.tsx wraps with AppShell
    documents/, chat/, team/, account/
  api/                      # Route Handlers = the BFF
    auth/*, me, documents, chat, conversations/*, team/members
  proxy.ts                  # route protection (redirects based on session-cookie presence)
lib/
  backend-fetch.ts          # server-only: cookies, auth header, 401 -> refresh -> retry
  api.ts                    # client-only: fetch wrapper for this app's own Route Handlers
  types.ts                  # mirrors the backend's Pydantic schemas by hand
hooks/                      # TanStack Query hooks (useDocuments, useChat, useTeam, ...)
components/
  ui/                       # shadcn primitives
  layout/                   # AppShell, Sidebar, Topbar, ThemeToggle
  documents/, chat/, team/, shared/
```

`lib/types.ts` is hand-written to match `src/docqa/schemas/*.py` exactly — not
generated. Route Handlers convert between the backend's `snake_case` JSON and this
app's `camelCase` types at the boundary; nothing past that boundary deals with
`snake_case`.

## Running it

```bash
npm install
cp .env.example .env.local   # API_BASE_URL defaults to http://localhost:8000
npm run dev
```

Needs the backend running (see the root README) — Postgres + Redis via
`docker compose up -d postgres redis`, then `uvicorn` and the Celery worker locally, or
the whole stack via `docker compose up`.

## What's built

All core pages: a public landing page, signup, login, Documents (upload + status
polling until `ready`/`failed`), Chat (conversation list, grounded answers with citation
chips, distinct styling for the backend's canned "not enough information" reply), Team
(list + admin-gated add-teammate dialog), and Account (profile, log out, log out
everywhere). Light/dark theme. Verified live end-to-end against the real backend stack,
including real NVIDIA/Pinecone-backed chat answers — not just built and linted.

**Not built this pass** (matches the backend's own Not Now list): a document
detail/chunk-viewer page, streaming chat responses, a mobile conversation-switcher with
full parity to desktop (mobile gets a "History" sheet instead of a persistent rail).

## Deployment (planned)

Intended target is Vercel (`API_BASE_URL` as a server-only env var pointing at wherever
the FastAPI backend ends up hosted — Compose on a small VPS, or a platform like Railway
or Fly.io that can run Postgres/Redis/a background worker). Not done yet — tracked as
the next step after the frontend itself was built.
