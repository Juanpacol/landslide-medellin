"""Classification of Alembic's state. PURE: no I/O, no DB.

Lives here and not in `domain/` on purpose: `domain/` is the territory and
the landslide risk rules, not deployment plumbing. But it follows the same
discipline — no I/O — so it's testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Status vocabulary from `agent_run_logs` (see monitoring/notify.py).
STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "critical"


class DriftKind(str, Enum):
    """Types of divergence between the repo's migrations and the DB's."""

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
    # False ⇒ `alembic upgrade head` would fail or corrupt: it must be skipped.
    safe_to_upgrade: bool = True


def diagnose(
    *,
    db_heads: tuple[str, ...],
    repo_heads: tuple[str, ...],
    known: frozenset[str],
    pending: list[str],
) -> Diagnosis:
    """Classifies the migration state.

    Args:
        db_heads: revisions in the `alembic_version` table
        repo_heads: head revisions present in `alembic/versions/`
        known: ALL revisions reachable in the repo
        pending: repo revisions not yet applied to the DB

    Returns:
        Diagnosis with severity and whether `upgrade head` is safe to run.
    """
    unknown = [rev for rev in db_heads if rev not in known]

    # FIRST, and the order matters: if the DB points to a revision not in
    # the repo, `pending` was computed over a broken chain and means
    # nothing. This is the real bug that took down the 6 crons on 2026-07-26.
    if unknown:
        return Diagnosis(
            kind=DriftKind.DB_AHEAD,
            status=STATUS_CRITICAL,
            safe_to_upgrade=False,
            summary=(
                f"DB ahead of code: revision {', '.join(unknown)} doesn't exist "
                f"in the repo. `alembic upgrade head` fails on every cron."
            ),
            detail={
                "db_heads": list(db_heads),
                "repo_heads": list(repo_heads),
                "unknown_revisions": unknown,
                "remediation": (
                    "commit and push the missing migration to main (see docs/RUNBOOK_MIGRATIONS.md)"
                ),
            },
        )

    # Two heads ⇒ alembic aborts with "Multiple head revisions are present".
    if len(repo_heads) > 1:
        return Diagnosis(
            kind=DriftKind.MULTIPLE_REPO_HEADS,
            status=STATUS_CRITICAL,
            safe_to_upgrade=False,
            summary=f"The repo has {len(repo_heads)} alembic heads: `upgrade head` is ambiguous.",
            detail={
                "repo_heads": list(repo_heads),
                "remediation": "alembic merge -m 'merge heads' " + " ".join(repo_heads),
            },
        )

    if not db_heads:
        return Diagnosis(
            kind=DriftKind.EMPTY_DB,
            status=STATUS_WARNING,
            summary="DB with no alembic_version: the full schema will be applied.",
            detail={"pending_count": len(pending)},
        )

    # Normal state between a merge to main and the next cron: the upgrade
    # SHOULD run (skipping it would leave the scraper writing against an
    # old schema). The silence on first detection is handled by the agent.
    if pending:
        return Diagnosis(
            kind=DriftKind.PENDING,
            status=STATUS_WARNING,
            summary=f"{len(pending)} repo migration(s) not yet applied to the DB.",
            detail={"pending": pending, "db_heads": list(db_heads)},
        )

    return Diagnosis(
        kind=DriftKind.OK,
        status=STATUS_OK,
        summary=f"Alembic in sync ({db_heads[0]}).",
        detail={"db_heads": list(db_heads)},
    )
