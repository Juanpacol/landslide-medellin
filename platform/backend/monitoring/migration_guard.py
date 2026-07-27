"""Agente: detecta drift entre las migraciones del repo y las de la BD.

Motivación (incidente 2026-07-26): se aplicó una migración a Supabase sin
commitear el archivo. `alembic_version` quedó apuntando a una revisión
inexistente en main y los 6 crons que corren `alembic upgrade head` fallaron
todos con "Can't locate revision". La ingesta se detuvo ~40 min sin que nadie
se enterara.

Modos:
    python -m monitoring.migration_guard                  # chequeo + alerta Slack
    python -m monitoring.migration_guard --offline        # solo repo, sin BD (CI)
    python -m monitoring.migration_guard --preflight --github-output
    python -m monitoring.migration_guard --json           # diagnóstico a stdout

Resultado → agent_run_logs (siempre que haya BD) + Slack solo si hay problema.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import ALERT_COOLDOWN_MIGRATION_GUARD_HOURS
from infrastructure.migrations.alembic_state import (
    RepoState,
    pending_revisions,
    read_db_heads,
    read_repo_state,
)
from infrastructure.migrations.diagnosis import (
    STATUS_CRITICAL,
    STATUS_OK,
    Diagnosis,
    DriftKind,
    diagnose,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "migration-drift-guard"

# Exit codes: 0 = seguir adelante; 2 = problema del repo que debe fallar el CI.
EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_REPO_PROBLEM = 2


def _diagnose_offline(repo: RepoState) -> Diagnosis:
    """Chequeo estático, sin BD: solo lo que se puede afirmar del repo solo.

    Se pasa db_heads vacío a propósito y se reinterpreta: sin BD no se puede
    hablar de "pendientes" ni de "BD adelante", únicamente de la integridad de
    la cadena de migraciones (heads múltiples, revisiones colgantes).
    """
    if len(repo.heads) > 1:
        return diagnose(
            db_heads=(), repo_heads=repo.heads, known=repo.known, pending=[]
        )
    return Diagnosis(
        kind=DriftKind.OK,
        status=STATUS_OK,
        summary=f"Cadena de migraciones íntegra: 1 head ({repo.heads[0]}), "
        f"{len(repo.known)} revisiones.",
        detail={"heads": list(repo.heads), "revisions": len(repo.known)},
    )


def _collect() -> Diagnosis:
    """Diagnóstico completo contra la BD."""
    repo = read_repo_state()
    db_heads = read_db_heads()
    # pending solo tiene sentido si toda revisión de la BD es resoluble;
    # con una desconocida, iterate_revisions lanzaría. diagnose() evalúa
    # DB_AHEAD primero, así que la lista vacía nunca se usa en ese caso.
    resolvable = all(rev in repo.known for rev in db_heads)
    pending = pending_revisions(db_heads, repo) if resolvable else []
    return diagnose(
        db_heads=db_heads, repo_heads=repo.heads, known=repo.known, pending=pending
    )


async def _should_alert(session: AsyncSession, dx: Diagnosis) -> bool:
    """Decide si mandar a Slack, o si solo registrar en agent_run_logs.

    Alerta en la TRANSICIÓN a un estado malo y luego como recordatorio cada
    ALERT_COOLDOWN_MIGRATION_GUARD_HOURS. Sin esto, con el guard corriendo
    cada ~15 min una avería de un día serían ~96 mensajes idénticos.
    """
    from db.models.agent_run_log import AgentRunLog

    result = await session.execute(
        select(AgentRunLog)
        .where(AgentRunLog.agent_name == AGENT_NAME)
        .order_by(AgentRunLog.created_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()

    if last is None or last.status == STATUS_OK:
        return True  # ok → malo: siempre avisar

    last_detail = last.detail or {}
    if last_detail.get("kind") != dx.kind.value:
        return True  # cambió el tipo de drift

    # PENDING es el estado normal entre un merge a main y el siguiente cron.
    # Solo es señal real si el MISMO conjunto sigue sin aplicarse.
    if dx.kind is DriftKind.PENDING and last_detail.get("pending") != dx.detail.get(
        "pending"
    ):
        return False

    created = last.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
    return age_hours >= ALERT_COOLDOWN_MIGRATION_GUARD_HOURS


async def _record(dx: Diagnosis, *, preflight: bool) -> None:
    """Persiste el resultado y alerta a Slack si corresponde."""
    from db.session import AsyncSessionLocal
    from monitoring.notify import fire_agent_alert, log_agent_run

    # `kind` va dentro de detail: _should_alert lo lee de la corrida anterior
    # para detectar transiciones entre tipos de drift.
    detail = {**dx.detail, "kind": dx.kind.value}

    async with AsyncSessionLocal() as session:
        if dx.status == STATUS_OK:
            # En preflight (cada ~15 min) no se escribe nada cuando todo está
            # bien: serían ~100 filas/día de ruido en agent_run_logs.
            if not preflight:
                await log_agent_run(
                    session, agent_name=AGENT_NAME, status=dx.status,
                    summary=dx.summary, detail=detail,
                )
            return

        if await _should_alert(session, dx):
            await fire_agent_alert(
                session, agent_name=AGENT_NAME, status=dx.status,
                summary=dx.summary, detail=detail,
            )
        else:
            await log_agent_run(
                session, agent_name=AGENT_NAME, status=dx.status,
                summary=dx.summary, detail=detail,
            )


def _write_github_output(dx: Diagnosis) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"kind={dx.kind.value}\n")
        fh.write(f"safe_to_upgrade={str(dx.safe_to_upgrade).lower()}\n")


async def run(
    *, offline: bool = False, preflight: bool = False,
    github_output: bool = False, as_json: bool = False,
) -> int:
    try:
        dx = _diagnose_offline(read_repo_state()) if offline else _collect()
    except Exception as exc:  # noqa: BLE001 - cualquier fallo debe ser visible
        logger.exception("migration guard falló: %s", exc)
        if github_output:
            # Sin diagnóstico no se puede decidir: se deja pasar el upgrade
            # para conservar el comportamiento previo al guard.
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write("kind=error\nsafe_to_upgrade=true\n")
        print(f"migration guard: ERROR — {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    if github_output:
        _write_github_output(dx)

    if as_json:
        print(json.dumps({
            "kind": dx.kind.value, "status": dx.status, "summary": dx.summary,
            "safe_to_upgrade": dx.safe_to_upgrade, "detail": dx.detail,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"[{dx.status.upper()}] {dx.summary}")

    if not offline:
        try:
            await _record(dx, preflight=preflight)
        except Exception as exc:  # noqa: BLE001
            # Registrar/alertar nunca debe tumbar la ingesta.
            logger.warning("no se pudo registrar el diagnóstico: %s", exc)

    # --preflight SIEMPRE sale 0: la decisión se toma con el output
    # safe_to_upgrade, y un guard que falla no puede detener la ingesta.
    if preflight:
        return EXIT_OK
    return EXIT_REPO_PROBLEM if dx.status == STATUS_CRITICAL else EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description="Guard de drift de migraciones alembic")
    parser.add_argument("--offline", action="store_true",
                        help="solo chequeos del repo, sin conectar a la BD")
    parser.add_argument("--preflight", action="store_true",
                        help="modo cron: nunca falla, expone safe_to_upgrade")
    parser.add_argument("--github-output", action="store_true",
                        help="escribe kind/safe_to_upgrade a $GITHUB_OUTPUT")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="imprime el diagnóstico completo en JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return asyncio.run(run(
        offline=args.offline, preflight=args.preflight,
        github_output=args.github_output, as_json=args.as_json,
    ))


if __name__ == "__main__":
    sys.exit(main())
