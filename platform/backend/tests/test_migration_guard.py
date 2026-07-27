"""Tests del guard de drift de migraciones.

Todo lo de `diagnosis` es puro: corre sin BD, sin red y sin secretos. Es
justamente por eso que la clasificación vive separada del I/O.
"""

from __future__ import annotations

from infrastructure.migrations.alembic_state import read_repo_state
from infrastructure.migrations.diagnosis import (
    STATUS_CRITICAL,
    STATUS_OK,
    STATUS_WARNING,
    DriftKind,
    diagnose,
)


class TestIncidenteReal:
    """Reproduce el incidente del 2026-07-26 que tumbó los 6 crons."""

    def test_revision_de_bd_ausente_en_repo(self) -> None:
        # La BD quedó en a1b2c3d4e5f6 tras aplicar la migración a mano, pero
        # el archivo nunca se commiteó: main solo conocía f8g9c0d1e2f3.
        dx = diagnose(
            db_heads=("a1b2c3d4e5f6",),
            repo_heads=("f8g9c0d1e2f3",),
            known=frozenset({"f8g9c0d1e2f3"}),
            pending=[],
        )

        assert dx.kind is DriftKind.DB_AHEAD
        assert dx.status == STATUS_CRITICAL
        # Lo que evita que los 6 crons mueran: se omite el upgrade.
        assert dx.safe_to_upgrade is False
        assert dx.detail["unknown_revisions"] == ["a1b2c3d4e5f6"]

    def test_db_ahead_tiene_precedencia_sobre_pending(self) -> None:
        # Si la revisión de la BD es desconocida, `pending` se calculó sobre
        # una cadena rota y no significa nada. DB_AHEAD debe ganar.
        dx = diagnose(
            db_heads=("desconocida",),
            repo_heads=("abc",),
            known=frozenset({"abc"}),
            pending=["abc"],
        )

        assert dx.kind is DriftKind.DB_AHEAD


class TestOtrosEstados:
    def test_sincronizado(self) -> None:
        dx = diagnose(
            db_heads=("abc",), repo_heads=("abc",), known=frozenset({"abc"}), pending=[]
        )

        assert dx.kind is DriftKind.OK
        assert dx.status == STATUS_OK
        assert dx.safe_to_upgrade is True

    def test_migraciones_pendientes_no_bloquean_el_upgrade(self) -> None:
        # Estado normal entre un merge a main y el siguiente cron: hay que
        # dejar correr el upgrade, si no el scraper escribe contra un esquema
        # viejo.
        dx = diagnose(
            db_heads=("abc",),
            repo_heads=("def",),
            known=frozenset({"abc", "def"}),
            pending=["def"],
        )

        assert dx.kind is DriftKind.PENDING
        assert dx.status == STATUS_WARNING
        assert dx.safe_to_upgrade is True

    def test_multiples_heads_es_ambiguo(self) -> None:
        dx = diagnose(
            db_heads=("abc",),
            repo_heads=("def", "ghi"),
            known=frozenset({"abc", "def", "ghi"}),
            pending=[],
        )

        assert dx.kind is DriftKind.MULTIPLE_REPO_HEADS
        assert dx.status == STATUS_CRITICAL
        assert dx.safe_to_upgrade is False

    def test_bd_virgen(self) -> None:
        dx = diagnose(
            db_heads=(), repo_heads=("abc",), known=frozenset({"abc"}), pending=["abc"]
        )

        assert dx.kind is DriftKind.EMPTY_DB
        assert dx.safe_to_upgrade is True


class TestRepoReal:
    """Integridad de alembic/versions/ tal como está en el repo. Sin BD."""

    def test_un_solo_head(self) -> None:
        # Un merge de dos ramas con migración deja dos heads y `alembic
        # upgrade head` aborta. Este test lo detecta en el PR.
        repo = read_repo_state()

        assert len(repo.heads) == 1, f"El repo tiene {len(repo.heads)} heads: {repo.heads}"

    def test_la_migracion_de_rls_esta_presente(self) -> None:
        # Regresión directa del incidente: si este archivo desaparece del
        # repo, la BD de producción vuelve a quedar adelante del código.
        repo = read_repo_state()

        assert "a1b2c3d4e5f6" in repo.known
