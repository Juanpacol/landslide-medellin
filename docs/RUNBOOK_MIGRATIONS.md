# Runbook — Migration Drift (Alembic ↔ Supabase)

You landed here from a `migration-drift-guard` Slack alert or a failed workflow. This document
gets you unblocked fast.

## Diagnosis

```bash
cd platform/backend && export PYTHONPATH=.
python -m monitoring.migration_guard --json
```

The `kind` field says what's going on:

| `kind` | What it means | Severity |
|---|---|---|
| `ok` | Repo and DB in sync | — |
| `db_ahead` | The DB has a revision that **does not exist in the repo** | 🚨 critical |
| `multiple_heads` | The repo has 2+ heads; `upgrade head` is ambiguous | 🚨 critical |
| `pending` | There are repo migrations not yet applied to the DB | ⚠️ normal if recent |
| `empty_db` | The DB has no `alembic_version` table | ⚠️ |

---

## `db_ahead` — the most common case

**What happened:** someone applied a migration to Supabase without committing the file.
`alembic_version` points to a revision GitHub Actions can't find when checking out `main`.

**Impact:** the 6 crons with `alembic upgrade head` would fail. Thanks to the guard **ingestion
keeps running** (the upgrade is skipped), but any new migration is blocked until this is fixed.

**Normal fix** — the file exists locally, it just needs pushing:

```bash
# The missing revision is in detail.unknown_revisions in the alert.
git status --short platform/backend/alembic/versions/
git add platform/backend/alembic/versions/<revision>_*.py
git commit -m "fix(db): commit migration <revision> applied to Supabase"
git push origin main
```

Repo and DB converge on their own on the next cron. Verify:

```bash
python -m monitoring.migration_guard --json   # should say kind: ok
```

**If the file was lost** (not on any machine): decide whether the DB rolls back or the repo
moves forward.

- If the schema introduced by that migration **is not needed**, point `alembic_version` to the
  last revision that IS in the repo:
  ```sql
  UPDATE alembic_version SET version_num = '<repo_revision>';
  ```
  ⚠️ Only if the DB's actual schema matches that revision. Otherwise, manually revert the
  objects the lost migration created.
- If the schema **is needed**, write a new migration that declares it and use `alembic stamp`
  to reconcile.

---

## `multiple_heads`

Happens when merging two branches that each added migrations in parallel.

```bash
cd platform/backend && export PYTHONPATH=.
alembic heads                       # see the heads
alembic merge -m "merge heads" <head1> <head2>
```

Commit the resulting merge migration. The `migration-guard` CI job blocks PRs that introduce
this state.

---

## `pending`

Normal right after merging a migration: the next cron applies it on its own (≤30 min with
SIATA). The guard **does not alert on the first detection** for this reason.

If it persists, something is blocking application — check the last cron's log. To force it:

```bash
cd platform/backend && export PYTHONPATH=. && alembic upgrade head
```

---

## The operating rule that avoids all of this

> **Apply migrations to Supabase only from already-pushed `main`.**

The correct sequence is: write the migration → commit → push → let the cron apply it (or run
`alembic upgrade head` **after** the push). Applying first and committing afterward is exactly
what caused the 2026-07-26 incident.

Note: there is **one** DB (Supabase) for GitHub Actions, local Docker and hand-run development.
There is no staging environment to make mistakes in without consequences.

---

## How the protection is built

| Piece | Where | What it does |
|---|---|---|
| `migration_guard` | `platform/backend/monitoring/migration_guard.py` | Diagnoses; alerts Slack only on transition or every 6h |
| State reading | `platform/backend/infrastructure/migrations/` | `alembic_state.py` (I/O) + `diagnosis.py` (pure) |
| Pre-flight in crons | `.github/actions/db-migrate/` | Skips the upgrade if unsafe; ingestion doesn't stop |
| Independent watch | `.github/workflows/monitor-api-health.yml` | Every 30 min, even if ingestion crons are down |
| Static PR check | `migration-guard` job in `ci-tests.yml` | Blocks multiple heads; no DB or secrets needed |
| Red-cron alert | `.github/actions/notify-failure/` | Slack when any workflow fails |
| Container startup | `platform/backend/docker-entrypoint.sh` | Starts anyway instead of crash-looping |

---

## DDL privilege separation

Three credentials, two roles. This is the real prevention for the 2026-07-26 incident: applying
a migration from a laptop is now impossible by construction, not by discipline.

| Variable | Role | DDL? | Lives in |
|---|---|---|---|
| `DATABASE_URL` / `DATABASE_URL_SYNC` | `teyva_app` | ❌ | local `.env`, repo secrets, all workflows |
| `DATABASE_URL_MIGRATE` | `postgres` | ✅ | **only** a GitHub Actions secret |

The policy lives in `platform/backend/infrastructure/migrations/ddl_url.py`, consumed by
`alembic/env.py`, `docker-entrypoint.sh` and the tests. Rule: `DATABASE_URL_MIGRATE` is used if
it exists; otherwise it falls back to `DATABASE_URL_SYNC` **only when the target is local**
(`localhost`, `db`, `127.0.0.1`), so offline `docker compose up` keeps migrating on its own.

### How to apply a migration now

`alembic upgrade head` against Supabase fails on purpose. The new loop — which is also better,
because it tests the migration against a disposable DB instead of the single production DB:

```bash
# 1. Disposable local schema
docker compose up -d db
cd platform/backend && export PYTHONPATH=.
export DATABASE_URL_SYNC=postgresql://teyva:teyva@localhost:5432/teyva
export DATABASE_URL=postgresql+asyncpg://teyva:teyva@localhost:5432/teyva
export DB_SSL=false

# 2. Generate and test both directions
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1 && alembic upgrade head

# 3. The only path to production
git push origin main
gh workflow run scraper-siata.yml   # "apply now" instead of waiting 30 min
```

Gotcha: `load_dotenv(override=False)` means the real environment wins over `.env`. If you
exported the local variables, they keep winning in that terminal —
`unset DATABASE_URL DATABASE_URL_SYNC` when going back to Supabase.

### Break-glass

Only from already-pushed `main`, and announced in Slack. The friction of going to the password
manager *is* the control:

```bash
DATABASE_URL_MIGRATE='postgresql://postgres.<REF>:<PWD>@aws-1-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require' \
  alembic upgrade head
```

### Diagnosis

| Symptom | Cause | Fix |
|---|---|---|
| `DDLNotAllowed` locally | Expected: the app role has no DDL | Use the loop above |
| `permission denied for schema public` in a cron | The `DATABASE_URL_MIGRATE` secret is wrong or expired | Check the secret |
| The guard says `pending` and never advances | `::warning::DATABASE_URL_MIGRATE missing` in the cron log | Configure the secret |

---

### What this does NOT prevent

- **Supabase's SQL Editor.** Anyone with dashboard access can run DDL by hand without going
  through Alembic — a vector *worse* than `alembic upgrade head`, because it isn't even recorded
  in `alembic_version`. Only `migration_guard` catches it, after the fact.
- **Someone with push access to `main`** can write a workflow that uses `DATABASE_URL_MIGRATE`
  for anything. It's a guardrail against accidents, not a defense against an insider.
- **Badly written migrations.** This prevents DDL *from the wrong place*, not *wrong* DDL. That's
  covered by testing upgrade + downgrade against the disposable local DB, which is the change's
  most valuable side benefit.
