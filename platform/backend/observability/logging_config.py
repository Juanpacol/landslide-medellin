"""Logging estructurado en JSON, consumible sin agente por DataDog/CloudWatch.

Reemplaza los `logging.basicConfig(...)` dispersos por cada script/módulo.
Sin acoplarse a ningún vendor: solo emite JSON a stdout, que es lo que ambos
consumen de forma nativa.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

_RESERVED_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Un objeto JSON por línea: timestamp, level, logger, message, ubicación
    y excepción si la hay. Campos extra pasados vía `logger.info(..., extra={...})`
    se incluyen tal cual (mismo patrón que `detail: dict` en agent_run_logs)."""

    def __init__(self, *, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key not in payload:
                try:
                    json.dumps(value)
                except TypeError:
                    value = str(value)
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str, *, level: int = logging.INFO) -> None:
    """Configura el logger raíz. Idempotente: llamarlo dos veces no duplica handlers.

    Formato controlado por `LOG_FORMAT=json|text` (default: json en
    `ENV=production`, text en dev — igual criterio de entorno que
    `api/auth.py`, sin importar de ahí para no crear una dependencia
    api→observability).
    """
    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)

    fmt = os.getenv("LOG_FORMAT", "").strip().lower()
    if not fmt:
        fmt = "json" if os.getenv("ENV") == "production" else "text"

    if fmt == "json":
        handler.setFormatter(JsonFormatter(service=service))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
