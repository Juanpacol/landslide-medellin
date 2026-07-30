# Troubleshooting

Known issues, consolidated from `CLAUDE.md`, `docs/RUNBOOK_MIGRATIONS.md`, and the codebase.

## GitHub Actions crons silently disabled

**Symptom:** a scraper or `predict-risk` cron stopped running; no failure notification.
**Cause:** GitHub disables scheduled workflows after 60 days without a commit to the repo
(`disabled_inactivity`).
**Fix:** run `gh workflow list` first whenever a data source looks stale — a disabled workflow
shows as such. Re-enable it (`gh workflow enable <name>`) and, ideally, commit something to keep
the repo active.

## Alembic drift between Supabase and the repo

**Symptom:** `alembic upgrade head` (or the CI migrate step) fails with `Can't locate revision`;
crons that depend on migrations start failing.
**Cause:** a migration was applied directly to Supabase and the corresponding code was committed
afterward, so `alembic_version` in the DB points to a revision the repo's history doesn't
recognize — or vice versa. This happened for real on 2026-07-26.
**Fix:** check drift with `python -m monitoring.migration_guard --json`. Follow
`docs/RUNBOOK_MIGRATIONS.md` for the resolution steps. Guardrail already in place:
`.github/actions/db-migrate` skips the upgrade step on drift and lets ingestion continue instead
of hard-failing the cron — but new migrations stay blocked until drift is resolved.
**Rule going forward:** apply migrations ONLY from already-pushed `main` — never apply to
Supabase and commit the migration afterward.

## Can't run `alembic upgrade head` from a laptop

**Symptom:** `alembic upgrade head` against Supabase fails with a permissions error even though
the app otherwise connects fine.
**Cause:** DDL privilege separation by design. The app role (`teyva_app`, used by
`DATABASE_URL`/`DATABASE_URL_SYNC`) cannot run DDL. Only `DATABASE_URL_MIGRATE` — a GitHub
Actions-only secret — can.
**Fix:** to create/test a migration, run it against the local Docker Compose Postgres instead.
See `infrastructure/migrations/ddl_url.py` for the policy and `docs/sql/ddl_privilege_split.sql`
for the setup SQL.

## Backend won't start in production

**Symptom:** the API process exits immediately when `ENV=production`.
**Cause:** `assert_production_auth` refuses to start a production instance with no `API_TOKEN`
configured — a deliberate safety gate, not a bug.
**Fix:** set `API_TOKEN` (and optionally `API_TOKEN_VIEWER` for the read-only role) before
deploying with `ENV=production`. In dev, an unset token is allowed with a warning logged.

## `.env` silently overriding the real environment

**Symptom:** `API_TOKEN` (or another var) behaves as if unset even though it's exported in the
shell/CI environment.
**Cause:** historically, an empty `API_TOKEN=` in a committed/local `.env` overwrote the real
env var.
**Fix:** `load_dotenv` calls now use `override=False` — the real environment always wins. If you
still see this, check for a stray `.env` with an empty value being loaded before the real env is
set.

## ML AUC-ROC 0.944 is not a valid metric

**Symptom:** the historical classifier metric looks strong (AUC 0.944, recall 0.999) but doesn't
hold up operationally.
**Cause:** the 26 positive labels came from synthetic events; once `is_synthetic` is filtered out
correctly, 0 usable positives remain — there is no real supervised target.
**Fix:** don't trust or re-report this metric. The declared susceptibility × trigger index
(`domain/susceptibility.py`, `ml/hazard.py`, combined via `application/neurosymbolic/infer.py`)
is the intended replacement — see `docs/research/audit-2026-07.md`.

## Scraper shows `records_valid=0` — is it broken?

**Symptom:** a scraper's log entry has `records_valid=0` and looks like a failed run.
**Cause:** scrapers dedupe by `source_row_id`; `records_valid=0` with an `ok` status just means
no NEW events arrived since the last run, not an error.
**Fix:** check `status` (in `GET /api/scraper/status` / `/health`), not `records_valid`, to judge
whether a scraper is actually failing. `GET /api/scraper/health` already classifies sources as
healthy/warning/critical using consecutive failures and staleness relative to the expected
interval.

## Rain alerts never fire / Snake Line looks flat

**Symptom:** `alert_log` stays empty, or the Soil Water Index / Snake Line barely moves despite
apparent rain.
**Watch for:** magnitude/unit inconsistencies between raw SIATA rain snapshots and historical
records feeding the same pipeline — if daily accumulations look implausible (near-zero or
orders-of-magnitude too large), suspect a unit/scale mismatch upstream rather than an alerting
bug. Verify against `rainfall_timeseries.precip_mm` directly and cross-check with
`GET /api/rain/live` before assuming the threshold/cooldown logic is at fault.
