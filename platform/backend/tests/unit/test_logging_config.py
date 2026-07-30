"""Tests puros de observability/logging_config.py. Sin BD, sin red."""

from __future__ import annotations

import json
import logging

from observability.logging_config import JsonFormatter, configure_logging


class TestJsonFormatter:
    def test_produce_json_valido_con_campos_esperados(self) -> None:
        formatter = JsonFormatter(service="test-service")
        record = logging.LogRecord(
            name="mi.logger",
            level=logging.INFO,
            pathname="x.py",
            lineno=10,
            msg="hola %s",
            args=("mundo",),
            exc_info=None,
        )

        parsed = json.loads(formatter.format(record))

        assert parsed["service"] == "test-service"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "mi.logger"
        assert parsed["message"] == "hola mundo"
        assert parsed["line"] == 10
        assert "timestamp" in parsed

    def test_incluye_stack_trace_en_excepciones(self) -> None:
        formatter = JsonFormatter(service="test-service")
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="x",
                level=logging.ERROR,
                pathname="x.py",
                lineno=1,
                msg="fallo",
                args=(),
                exc_info=sys.exc_info(),
            )
        parsed = json.loads(formatter.format(record))

        assert "ValueError: boom" in parsed["stack_trace"]

    def test_incluye_campos_extra(self) -> None:
        formatter = JsonFormatter(service="test-service")
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="msg",
            args=(),
            exc_info=None,
        )
        record.op = "predict_risk"
        record.category = "transient"

        parsed = json.loads(formatter.format(record))

        assert parsed["op"] == "predict_risk"
        assert parsed["category"] == "transient"


class TestConfigureLogging:
    def test_es_idempotente(self) -> None:
        configure_logging("svc-a")
        n1 = len(logging.getLogger().handlers)
        configure_logging("svc-a")
        n2 = len(logging.getLogger().handlers)

        assert n1 == n2 == 1
