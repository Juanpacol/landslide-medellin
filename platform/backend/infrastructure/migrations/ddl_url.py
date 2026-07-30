"""DDL credential policy: which one migrates, and when it's allowed.

Privilege separation (2026-07-26 incident, see docs/RUNBOOK_MIGRATIONS.md):
the application role can't run DDL, and the credential that can lives only
as a GitHub Actions secret. That way, applying a migration from a laptop is
impossible by construction, not by discipline.

The problem this module solves: Alembic and the rest of the sync code (the
guard, ml/train, the entrypoint's ping) used to share `DATABASE_URL_SYNC`,
so there was no way to distinguish a "DML-only sync connection" from a
"sync connection for DDL". `DATABASE_URL_MIGRATE` is introduced for that.

Falling back to `DATABASE_URL_SYNC` is allowed ONLY against a local
database: there the user owns the schema and offline `docker compose up`
must keep migrating on its own. Against Supabase, DDLNotAllowed is raised
with instructions, instead of letting psycopg2 fail mid-migration with
"permission denied for schema public", which is considerably worse.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy.engine import make_url

MIGRATE_VAR = "DATABASE_URL_MIGRATE"
SYNC_VAR = "DATABASE_URL_SYNC"

# `db` is the Postgres service name in docker-compose (offline fallback).
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "db", "host.docker.internal"})

_HELP = """
No migration credential available (DDL privilege separation).

{reason}

This is intentional — see docs/RUNBOOK_MIGRATIONS.md.

To APPLY a migration to Supabase:
    git push origin main                  # the next cron applies it (≤30 min)
    gh workflow run scraper-siata.yml     # or force it now

To CREATE or TEST a migration, use the disposable local DB:
    docker compose up -d db
    export DATABASE_URL_SYNC=postgresql://teyva:teyva@localhost:5432/teyva
    export DATABASE_URL=postgresql+asyncpg://teyva:teyva@localhost:5432/teyva
    export DB_SSL=false
    alembic upgrade head
    alembic revision --autogenerate -m "description"
""".strip()


class DDLNotAllowed(RuntimeError):
    """No DDL credential available and the target isn't a local database."""


def is_local_target(url: str) -> bool:
    """Does the URL point to a local database? Pure, no I/O."""
    if not url:
        return False
    try:
        host = (make_url(url).host or "").strip().lower()
    except Exception:  # noqa: BLE001 — a malformed URL isn't "local"
        return False
    return host in LOCAL_HOSTS


def resolve_migration_url(env: Mapping[str, str] | None = None) -> str:
    """URL to run DDL with.

    Priority: DATABASE_URL_MIGRATE → DATABASE_URL_SYNC, but the latter only
    if the target is local.

    Raises:
        DDLNotAllowed: if there's no migration credential and the target is remote.
    """
    env = os.environ if env is None else env

    migrate_url = (env.get(MIGRATE_VAR) or "").strip()
    if migrate_url:
        return migrate_url

    sync_url = (env.get(SYNC_VAR) or "").strip()
    if not sync_url:
        raise DDLNotAllowed(_HELP.format(reason=f"Neither {MIGRATE_VAR} nor {SYNC_VAR} is set."))

    if is_local_target(sync_url):
        return sync_url

    host = make_url(sync_url).host or "unknown"
    raise DDLNotAllowed(
        _HELP.format(
            reason=(
                f"{MIGRATE_VAR} isn't set and {SYNC_VAR} points to a remote DB\n"
                f"({host}) with the application role, which CANNOT do DDL."
            )
        )
    )


def can_run_ddl(env: Mapping[str, str] | None = None) -> bool:
    """Boolean version of `resolve_migration_url`, for the entrypoint's shell."""
    try:
        resolve_migration_url(env)
    except DDLNotAllowed:
        return False
    return True
