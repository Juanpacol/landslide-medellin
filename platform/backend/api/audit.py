"""
Helper de auditoría para endpoints sensibles.

Se llama EXPLÍCITAMENTE en cada endpoint auditado (no interceptor global):
así queda visible en el propio handler qué se registra y con qué resumen.
El payload nunca se guarda crudo (puede contener secretos, ej. URL de
webhook) — solo su SHA-256 y un resumen legible sin datos sensibles.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.rate_limit import _client_ip
from db.models.audit_log import AuditLog


def _hash_payload(payload: Any) -> str | None:
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def log_audit_event(
    session: AsyncSession,
    request: Request,
    *,
    action: str,
    resource: str | None = None,
    payload: Any = None,
    summary: str | None = None,
) -> None:
    """Agrega la fila de auditoría a la sesión (el commit lo hace el endpoint,
    en la misma transacción que el cambio auditado — o ambos o ninguno)."""
    session.add(
        AuditLog(
            actor=f"token@{_client_ip(request)}",
            action=action,
            resource=resource,
            payload_hash=_hash_payload(payload),
            summary=summary,
        )
    )
