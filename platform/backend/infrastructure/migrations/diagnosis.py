"""Clasificación del estado de Alembic. PURO: sin I/O, sin BD.

Vive aquí y no en `domain/` a propósito: `domain/` es el territorio y las
reglas de riesgo de deslizamiento, no plomería de despliegue. Pero sigue la
misma disciplina — nada de I/O — para que sea testeable sin base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Vocabulario de estados de `agent_run_logs` (ver monitoring/notify.py).
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"


class DriftKind(str, Enum):
    """Tipos de divergencia entre las migraciones del repo y las de la BD."""

    OK = "ok"
    DB_AHEAD = "db_ahead"
    PENDING = "pending"
    MULTIPLE_REPO_HEADS = "multiple_heads"
    EMPTY_DB = "empty_db"


@dataclass(frozen=True)
class Diagnosis:
    kind: DriftKind
    status: str
    summary: str
    detail: dict = field(default_factory=dict)
    # False ⇒ `alembic upgrade head` fallaría o corrompería: hay que omitirlo.
    safe_to_upgrade: bool = True


def diagnose(
    *,
    db_heads: tuple[str, ...],
    repo_heads: tuple[str, ...],
    known: frozenset[str],
    pending: list[str],
) -> Diagnosis:
    """Clasifica el estado de las migraciones.

    Args:
        db_heads: revisiones en la tabla `alembic_version`
        repo_heads: revisiones head presentes en `alembic/versions/`
        known: TODAS las revisiones alcanzables en el repo
        pending: revisiones del repo aún no aplicadas en la BD

    Returns:
        Diagnosis con severidad y si es seguro correr `upgrade head`.
    """
    unknown = [rev for rev in db_heads if rev not in known]

    # PRIMERO, y el orden importa: si la BD apunta a una revisión que no está
    # en el repo, `pending` se calculó sobre una cadena rota y no significa
    # nada. Este es el bug real que tumbó los 6 crons el 2026-07-26.
    if unknown:
        return Diagnosis(
            kind=DriftKind.DB_AHEAD,
            status=STATUS_CRITICAL,
            safe_to_upgrade=False,
            summary=(
                f"BD adelante del código: la revisión {', '.join(unknown)} no existe "
                f"en el repo. `alembic upgrade head` falla en todos los crons."
            ),
            detail={
                "db_heads": list(db_heads),
                "repo_heads": list(repo_heads),
                "unknown_revisions": unknown,
                "remediation": (
                    "commitear y pushear la migración faltante a main "
                    "(ver docs/RUNBOOK_MIGRATIONS.md)"
                ),
            },
        )

    # Dos heads ⇒ alembic aborta con "Multiple head revisions are present".
    if len(repo_heads) > 1:
        return Diagnosis(
            kind=DriftKind.MULTIPLE_REPO_HEADS,
            status=STATUS_CRITICAL,
            safe_to_upgrade=False,
            summary=f"El repo tiene {len(repo_heads)} heads de alembic: `upgrade head` es ambiguo.",
            detail={
                "repo_heads": list(repo_heads),
                "remediation": "alembic merge -m 'merge heads' " + " ".join(repo_heads),
            },
        )

    if not db_heads:
        return Diagnosis(
            kind=DriftKind.EMPTY_DB,
            status=STATUS_WARNING,
            summary="BD sin alembic_version: se aplicará el esquema completo.",
            detail={"pending_count": len(pending)},
        )

    # Estado normal entre un merge a main y el siguiente cron: el upgrade SÍ
    # debe correr (omitirlo dejaría al scraper escribiendo contra un esquema
    # viejo). El silencio de la primera detección lo maneja el agente.
    if pending:
        return Diagnosis(
            kind=DriftKind.PENDING,
            status=STATUS_WARNING,
            summary=f"{len(pending)} migración(es) del repo sin aplicar en la BD.",
            detail={"pending": pending, "db_heads": list(db_heads)},
        )

    return Diagnosis(
        kind=DriftKind.OK,
        status=STATUS_OK,
        summary=f"Alembic sincronizado ({db_heads[0]}).",
        detail={"db_heads": list(db_heads)},
    )
