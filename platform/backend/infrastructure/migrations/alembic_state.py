"""Lee el estado de Alembic del repo y de la BD vía la API de Alembic.

Nada de parsear la salida de `alembic current` o `alembic heads`: esa salida
es para humanos y cambia entre versiones. `ScriptDirectory` y
`MigrationContext` son la API estable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

# .../platform/backend — dos niveles arriba de infrastructure/migrations/.
BACKEND_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RepoState:
    """Migraciones presentes en el checkout actual."""

    heads: tuple[str, ...]
    known: frozenset[str]


def _script_directory() -> ScriptDirectory:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # alembic.ini trae `script_location = alembic` (relativo al cwd). El guard
    # corre con cwd distintos — los crons usan working-directory, el
    # docker-entrypoint no — así que se fuerza la ruta absoluta.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def read_repo_state() -> RepoState:
    """Revisiones del repo. NO toca la base de datos."""
    script = _script_directory()
    # walk_revisions() recorre base→heads: el conjunto resultante es
    # exactamente "lo que alembic sabe resolver". Una migración aplicada a la
    # BD pero nunca commiteada NO aparece aquí — así se detecta el drift.
    known = frozenset(sc.revision for sc in script.walk_revisions())
    return RepoState(heads=tuple(script.get_heads()), known=known)


def read_db_heads() -> tuple[str, ...]:
    """Revisiones en la tabla `alembic_version`.

    Se usa get_current_heads() y no get_current_revision(): devuelve () en una
    BD virgen (tabla inexistente) y tolera múltiples filas sin lanzar.
    """
    from db.session import sync_engine

    with sync_engine.connect() as conn:
        return tuple(MigrationContext.configure(conn).get_current_heads())


def pending_revisions(db_heads: tuple[str, ...], repo: RepoState) -> list[str]:
    """Revisiones del repo que la BD todavía no aplicó.

    Precondición: todas las `db_heads` deben estar en `repo.known`. Con una
    revisión desconocida, iterate_revisions lanzaría — por eso quien llama
    verifica primero (ver diagnosis.diagnose, que evalúa DB_AHEAD antes).
    """
    script = _script_directory()
    applied: set[str] = set()
    for head in db_heads:
        applied |= {sc.revision for sc in script.iterate_revisions(head, "base")}
    return sorted(repo.known - applied)
