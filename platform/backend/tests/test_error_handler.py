"""Tests puros de errors/error_handler.py. Sin BD, sin red."""

from __future__ import annotations

import pytest

from errors.error_handler import (
    BusinessError,
    TransientError,
    ValidationError,
    handle_errors,
    retry_transient_call,
)

pytestmark = pytest.mark.asyncio


class TestRetryTransientCall:
    async def test_reintenta_hasta_agotar_intentos(self) -> None:
        calls = 0

        async def _factory():
            nonlocal calls
            calls += 1
            raise TransientError("caido")

        with pytest.raises(TransientError):
            await retry_transient_call(_factory, attempts=3, base_delay_s=0.001)

        assert calls == 3

    async def test_retorna_al_primer_exito(self) -> None:
        calls = 0

        async def _factory():
            nonlocal calls
            calls += 1
            if calls < 2:
                raise TransientError("caido")
            return "ok"

        result = await retry_transient_call(_factory, attempts=3, base_delay_s=0.001)

        assert result == "ok"
        assert calls == 2

    async def test_no_reintenta_excepciones_no_listadas(self) -> None:
        calls = 0

        async def _factory():
            nonlocal calls
            calls += 1
            raise ValueError("no transitorio")

        with pytest.raises(ValueError):
            await retry_transient_call(_factory, attempts=3, base_delay_s=0.001)

        assert calls == 1


class TestHandleErrors:
    async def test_validation_error_se_relanza(self) -> None:
        @handle_errors("op_test", fallback="fallback")
        async def _fn():
            raise ValidationError("entrada inválida")

        with pytest.raises(ValidationError):
            await _fn()

    async def test_business_error_devuelve_fallback(self) -> None:
        @handle_errors("op_test", fallback="fallback")
        async def _fn():
            raise BusinessError("comuna sin predicción")

        assert await _fn() == "fallback"

    async def test_excepcion_no_clasificada_devuelve_fallback(self) -> None:
        @handle_errors("op_test", fallback="fallback")
        async def _fn():
            raise RuntimeError("boom")

        assert await _fn() == "fallback"

    async def test_transient_con_retries_reintenta_y_devuelve_fallback(self) -> None:
        calls = 0

        @handle_errors("op_test", fallback="fallback", retries=3)
        async def _fn():
            nonlocal calls
            calls += 1
            raise TransientError("caido")

        assert await _fn() == "fallback"
        assert calls == 3

    async def test_exito_normal_pasa_directo(self) -> None:
        @handle_errors("op_test", fallback="fallback")
        async def _fn():
            return "real"

        assert await _fn() == "real"
