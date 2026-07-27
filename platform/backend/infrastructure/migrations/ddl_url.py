"""Política de credenciales para DDL: con cuál se migra y cuándo está permitido.

Separación de privilegios (incidente 2026-07-26, ver docs/RUNBOOK_MIGRATIONS.md):
el rol de la aplicación no puede ejecutar DDL, y la credencial que sí puede vive
únicamente como secret de GitHub Actions. Así, aplicar una migración desde un
portátil es imposible por construcción, no por disciplina.

El problema que resuelve este módulo: hoy Alembic y el resto del código sync
(el guard, ml/train, el ping del entrypoint) comparten `DATABASE_URL_SYNC`, así
que no hay forma de distinguir "conexión sync de solo DML" de "conexión sync
para DDL". Se introduce `DATABASE_URL_MIGRATE` para eso.

El fallback a `DATABASE_URL_SYNC` se permite SOLO contra una base local: ahí el
usuario es dueño del esquema y `docker compose up` offline debe seguir migrando
solo. Contra Supabase se lanza DDLNotAllowed con instrucciones, en vez de
dejar que psycopg2 falle a mitad de una migración con "permission denied for
schema public", que es bastante peor.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from sqlalchemy.engine import make_url

MIGRATE_VAR = "DATABASE_URL_MIGRATE"
SYNC_VAR = "DATABASE_URL_SYNC"

# `db` es el nombre del servicio Postgres en docker-compose (fallback offline).
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1", "db", "host.docker.internal"})

_HELP = """
No hay credencial de migración (separación de privilegios DDL).

{reason}

Esto es intencional — ver docs/RUNBOOK_MIGRATIONS.md.

Para APLICAR una migración a Supabase:
    git push origin main                  # el próximo cron la aplica (≤30 min)
    gh workflow run scraper-siata.yml     # o fuérzalo ahora

Para CREAR o PROBAR una migración, usa la BD local desechable:
    docker compose up -d db
    export DATABASE_URL_SYNC=postgresql://teyva:teyva@localhost:5432/teyva
    export DATABASE_URL=postgresql+asyncpg://teyva:teyva@localhost:5432/teyva
    export DB_SSL=false
    alembic upgrade head
    alembic revision --autogenerate -m "descripción"
""".strip()


class DDLNotAllowed(RuntimeError):
    """No hay credencial DDL y el destino no es una base local."""


def is_local_target(url: str) -> bool:
    """¿La URL apunta a una base local? Puro, sin I/O."""
    if not url:
        return False
    try:
        host = (make_url(url).host or "").strip().lower()
    except Exception:  # noqa: BLE001 — una URL corrupta no es "local"
        return False
    return host in LOCAL_HOSTS


def resolve_migration_url(env: Mapping[str, str] | None = None) -> str:
    """URL con la que ejecutar DDL.

    Prioridad: DATABASE_URL_MIGRATE → DATABASE_URL_SYNC, pero esta última solo
    si el destino es local.

    Raises:
        DDLNotAllowed: si no hay credencial de migración y el destino es remoto.
    """
    env = os.environ if env is None else env

    migrate_url = (env.get(MIGRATE_VAR) or "").strip()
    if migrate_url:
        return migrate_url

    sync_url = (env.get(SYNC_VAR) or "").strip()
    if not sync_url:
        raise DDLNotAllowed(_HELP.format(reason=f"Ni {MIGRATE_VAR} ni {SYNC_VAR} están definidas."))

    if is_local_target(sync_url):
        return sync_url

    host = make_url(sync_url).host or "desconocido"
    raise DDLNotAllowed(
        _HELP.format(
            reason=(
                f"{MIGRATE_VAR} no está definida y {SYNC_VAR} apunta a una BD remota\n"
                f"({host}) con el rol de aplicación, que NO puede hacer DDL."
            )
        )
    )


def can_run_ddl(env: Mapping[str, str] | None = None) -> bool:
    """Versión booleana de `resolve_migration_url`, para el shell del entrypoint."""
    try:
        resolve_migration_url(env)
    except DDLNotAllowed:
        return False
    return True
