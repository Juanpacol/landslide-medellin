"""Tests puros de application/orchestrator.py. Sin BD, sin red."""

from __future__ import annotations

import pytest

from application.orchestrator import Step, run_steps
from errors.error_handler import TransientError

pytestmark = pytest.mark.asyncio


class TestRunSteps:
    async def test_todos_los_pasos_ok(self) -> None:
        calls: list[str] = []

        async def _a():
            calls.append("a")

        async def _b():
            calls.append("b")

        results = await run_steps([Step("a", _a), Step("b", _b)])

        assert [r.status for r in results] == ["ok", "ok"]
        assert calls == ["a", "b"]

    async def test_un_paso_fallido_no_bloquea_a_los_demas(self) -> None:
        calls: list[str] = []

        async def _fails():
            raise RuntimeError("boom")

        async def _b():
            calls.append("b")

        results = await run_steps([Step("a", _fails), Step("b", _b)])

        assert results[0].status == "error"
        assert results[1].status == "ok"
        assert calls == ["b"]  # b corrió pese al fallo de a

    async def test_respeta_orden_topologico(self) -> None:
        order: list[str] = []

        async def _make(name):
            async def _fn():
                order.append(name)

            return _fn

        results = await run_steps(
            [
                Step("second", await _make("second"), depends_on=("first",)),
                Step("first", await _make("first")),
            ]
        )

        assert order == ["first", "second"]
        assert [r.name for r in results] == ["first", "second"]

    async def test_dependiente_de_critico_fallido_se_salta(self) -> None:
        calls: list[str] = []

        async def _fails():
            raise RuntimeError("boom")

        async def _dependent():
            calls.append("dependent")

        results = await run_steps(
            [
                Step("critical_step", _fails, critical=True),
                Step("dependent_step", _dependent, depends_on=("critical_step",)),
            ]
        )

        by_name = {r.name: r for r in results}
        assert by_name["critical_step"].status == "error"
        assert by_name["dependent_step"].status == "skipped"
        assert calls == []

    async def test_dependiente_de_no_critico_fallido_igual_corre(self) -> None:
        calls: list[str] = []

        async def _fails():
            raise RuntimeError("boom")

        async def _dependent():
            calls.append("dependent")

        results = await run_steps(
            [
                Step("noncritical_step", _fails, critical=False),
                Step("dependent_step", _dependent, depends_on=("noncritical_step",)),
            ]
        )

        by_name = {r.name: r for r in results}
        assert by_name["noncritical_step"].status == "error"
        assert by_name["dependent_step"].status == "ok"
        assert calls == ["dependent"]

    async def test_retries_reintenta_transient_error(self) -> None:
        attempts = 0

        async def _flaky():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TransientError("caído")

        results = await run_steps([Step("flaky", _flaky, retries=3)])

        assert results[0].status == "ok"
        assert attempts == 3

    async def test_duration_ms_se_registra(self) -> None:
        async def _fast():
            return None

        results = await run_steps([Step("fast", _fast)])

        assert results[0].duration_ms >= 0
