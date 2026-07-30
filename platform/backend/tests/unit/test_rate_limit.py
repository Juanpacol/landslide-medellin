"""Tests puros de rate limiting. Sin BD, sin red, sin FastAPI TestClient."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.rate_limit import _hits, rate_limit_by_session


@pytest.fixture(autouse=True)
def _clean_hits():
    _hits.clear()
    yield
    _hits.clear()


class TestRateLimitBySession:
    def test_permite_hasta_el_limite(self) -> None:
        for _ in range(5):
            rate_limit_by_session("test_scope", "session-a", times=5, seconds=60)

    def test_bloquea_al_superar_el_limite(self) -> None:
        for _ in range(5):
            rate_limit_by_session("test_scope", "session-a", times=5, seconds=60)

        with pytest.raises(HTTPException) as exc_info:
            rate_limit_by_session("test_scope", "session-a", times=5, seconds=60)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

    def test_sesiones_distintas_no_comparten_ventana(self) -> None:
        for _ in range(5):
            rate_limit_by_session("test_scope", "session-a", times=5, seconds=60)

        # session-b no debe verse afectada por el límite agotado de session-a.
        rate_limit_by_session("test_scope", "session-b", times=5, seconds=60)

    def test_scope_distinto_no_comparte_ventana_con_ip(self) -> None:
        # Un scope como "chat_session" no debe colisionar con "chat" (por IP)
        # aunque compartan el mismo dict _hits.
        for _ in range(5):
            rate_limit_by_session("chat_session", "1.2.3.4", times=5, seconds=60)

        rate_limit_by_session("chat", "1.2.3.4", times=5, seconds=60)
