"""
Audit helper for sensitive endpoints.

Called EXPLICITLY in each audited endpoint (no global interceptor): that
way it's visible right in the handler what gets logged and with what
summary. The payload is never stored raw (it can contain secrets, e.g. a
webhook URL) — only its SHA-256 and a readable summary with no sensitive data.
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
    """Adds the audit row to the session (the endpoint does the commit, in
    the same transaction as the audited change — both or neither)."""
    session.add(
        AuditLog(
            actor=f"token@{_client_ip(request)}",
            action=action,
            resource=resource,
            payload_hash=_hash_payload(payload),
            summary=summary,
        )
    )
