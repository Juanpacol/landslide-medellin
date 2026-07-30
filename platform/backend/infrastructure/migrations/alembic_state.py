"""Reads Alembic's repo and DB state via Alembic's API.

No parsing of `alembic current` or `alembic heads` output: that output is
for humans and changes between versions. `ScriptDirectory` and
`MigrationContext` are the stable API.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

# .../platform/backend — two levels above infrastructure/migrations/.
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RepoState:
    """Migrations present in the current checkout."""

    heads: tuple[str, ...]
    known: frozenset[str]


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # alembic.ini has `script_location = alembic` (relative to cwd). The
    # guard runs with different cwds — crons use working-directory, the
    # docker-entrypoint doesn't — so the absolute path is forced.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def read_repo_state() -> RepoState:
    """Repo revisions. Does NOT touch the database."""
    script = _script_directory()
    # walk_revisions() walks base→heads: the resulting set is exactly "what
    # alembic knows how to resolve". A migration applied to the DB but
    # never committed does NOT appear here — that's how drift is detected.
    known = frozenset(sc.revision for sc in script.walk_revisions())
    return RepoState(heads=tuple(script.get_heads()), known=known)


def read_db_heads() -> tuple[str, ...]:
    """Revisions in the `alembic_version` table.

    Uses get_current_heads(), not get_current_revision(): returns () on a
    fresh DB (table doesn't exist) and tolerates multiple rows without raising.
    """
    from db.session import sync_engine

    with sync_engine.connect() as conn:
        return tuple(MigrationContext.configure(conn).get_current_heads())


def pending_revisions(db_heads: tuple[str, ...], repo: RepoState) -> list[str]:
    """Repo revisions the DB hasn't applied yet.

    Precondition: every `db_heads` entry must be in `repo.known`. With an
    unknown revision, iterate_revisions would raise — that's why the
    caller checks first (see diagnosis.diagnose, which evaluates DB_AHEAD
    before this).
    """
    script = _script_directory()
    applied: set[str] = set()
    for head in db_heads:
        applied |= {sc.revision for sc in script.iterate_revisions(head, "base")}
    return sorted(repo.known - applied)
