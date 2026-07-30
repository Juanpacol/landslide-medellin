# Quick Start

Get the TEYVA stack running locally in under 5 minutes.

## Option A — Docker (recommended)

```bash
docker compose up
```

Then open http://localhost:3000 (frontend). The backend API is at http://localhost:8000.

This starts: `db` (Postgres, offline fallback only — see note below), `ollama`, `backend`,
`frontend`, `scraper`, and `ml`.

> The project's real database is Supabase (Postgres via the Session-mode connection pooler).
> Docker's `db` service is only used if the root `.env` does **not** define `DATABASE_URL`. See
> `CLAUDE.md` → "Database — ONE single source of truth".

## Option B — Manual (no Docker)

### Backend

```bash
cd platform/backend
export PYTHONPATH=.
uvicorn api.main:app --reload --port 8000
```

Other backend entrypoints:

```bash
python -m ml.predict         # batch risk predictions for all communes
python -m scraper.scheduler  # scraper daemon + health watchdog
alembic upgrade head         # apply DB migrations (local Postgres only — see below)
```

### Frontend

```bash
cd platform/frontend
pnpm dev
```

## Prerequisites

- Python 3.11+, `PYTHONPATH=platform/backend` for all backend commands (it's a single package —
  modules import as top-level, e.g. `from domain.communes import ...`).
- Node.js + `pnpm` for the frontend (Next.js 16 + React 19).
- A `DATABASE_URL` / `DATABASE_URL_SYNC` pointing at Supabase's pooler
  (`aws-1-us-west-2.pooler.supabase.com:5432`, `DB_SSL=true`), or rely on the Docker fallback `db`.

## Gotchas

- **Migrations from a laptop will fail against Supabase by design**: the app role
  (`teyva_app`, used by `DATABASE_URL`) has no DDL privileges. `alembic upgrade head` only works
  against the local Docker Postgres, or in CI via the `DATABASE_URL_MIGRATE` secret. See
  `docs/RUNBOOK_MIGRATIONS.md`.
- `ENV=production` without `API_TOKEN` set makes the backend refuse to start
  (`assert_production_auth`). In dev, no token = open access with a warning logged.
- See `docs/troubleshooting.md` for more.

## Next steps

- `docs/architecture.md` — folder layout and data flow.
- `docs/api.md` — REST endpoints.
- `docs/GUIDE.md` — full documentation index.
