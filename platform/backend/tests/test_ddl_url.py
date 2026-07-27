"""Tests puros de la política de credenciales DDL. Sin BD, sin red.

Cubre la regla central de la separación de privilegios: contra una BD remota
sin DATABASE_URL_MIGRATE, migrar debe ser imposible; contra una BD local
(docker-compose offline, Postgres del portátil) debe seguir funcionando igual.
"""

from __future__ import annotations

import pytest

from infrastructure.migrations.ddl_url import (
    DDLNotAllowed,
    can_run_ddl,
    is_local_target,
    resolve_migration_url,
)

SUPABASE = "postgresql://teyva_app.ref:pwd@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
LOCAL_COMPOSE = "postgresql://teyva:teyva@db:5432/teyva"
LOCALHOST = "postgresql://teyva:teyva@localhost:5432/teyva"
MIGRATE = "postgresql://postgres.ref:otra@aws-1-us-west-2.pooler.supabase.com:5432/postgres"


class TestIsLocalTarget:
    @pytest.mark.parametrize("url", [LOCAL_COMPOSE, LOCALHOST, "postgresql://u:p@127.0.0.1/db"])
    def test_local(self, url: str) -> None:
        assert is_local_target(url) is True

    @pytest.mark.parametrize("url", [SUPABASE, "postgresql://u:p@db.ref.supabase.co/postgres"])
    def test_remoto(self, url: str) -> None:
        assert is_local_target(url) is False

    def test_url_vacia_o_corrupta_no_es_local(self) -> None:
        assert is_local_target("") is False
        assert is_local_target("no-es-una-url::://") is False


class TestResolveMigrationUrl:
    def test_prefiere_migrate_url(self) -> None:
        env = {"DATABASE_URL_MIGRATE": MIGRATE, "DATABASE_URL_SYNC": SUPABASE}
        assert resolve_migration_url(env) == MIGRATE

    def test_remoto_sin_migrate_url_lanza(self) -> None:
        # El caso que hace imposible el incidente del 2026-07-26.
        with pytest.raises(DDLNotAllowed) as exc:
            resolve_migration_url({"DATABASE_URL_SYNC": SUPABASE})
        # El mensaje debe enseñar el flujo, no solo negarse.
        assert "git push origin main" in str(exc.value)
        assert "docker compose up -d db" in str(exc.value)

    @pytest.mark.parametrize("url", [LOCAL_COMPOSE, LOCALHOST])
    def test_local_sin_migrate_url_funciona(self, url: str) -> None:
        # docker-compose offline y el loop de desarrollo no se rompen.
        assert resolve_migration_url({"DATABASE_URL_SYNC": url}) == url

    def test_sin_ninguna_variable_lanza(self) -> None:
        with pytest.raises(DDLNotAllowed):
            resolve_migration_url({})

    def test_migrate_url_vacia_cae_al_fallback(self) -> None:
        env = {"DATABASE_URL_MIGRATE": "  ", "DATABASE_URL_SYNC": LOCALHOST}
        assert resolve_migration_url(env) == LOCALHOST


class TestCanRunDdl:
    def test_true_con_migrate_url(self) -> None:
        assert can_run_ddl({"DATABASE_URL_MIGRATE": MIGRATE}) is True

    def test_true_en_local(self) -> None:
        assert can_run_ddl({"DATABASE_URL_SYNC": LOCAL_COMPOSE}) is True

    def test_false_en_remoto_sin_credencial(self) -> None:
        assert can_run_ddl({"DATABASE_URL_SYNC": SUPABASE}) is False
