"""Helper compartido para notificaciones de agentes.

Arma payloads Slack y persiste resultados en agent_run_logs.
Un fallo de Slack NUNCA tumba la corrida del agente (regla existente).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.agent_run_log import AgentRunLog
from infrastructure.external.slack_client import post_webhook

logger = logging.getLogger(__name__)


async def log_agent_run(
    session: AsyncSession,
    *,
    agent_name: str,
    status: str,
    summary: str | None = None,
    detail: dict | None = None,
    run_started_at: datetime | None = None,
    run_finished_at: datetime | None = None,
) -> None:
    """Persiste resultado de corrida de agente en agent_run_logs.

    Args:
        session: sesión async de BD
        agent_name: nombre del agente (ej. "ml-drift-detector")
        status: "ok", "warning", "critical", o "error"
        summary: descripción breve del resultado
        detail: dict con hallazgos estructurados (opcional)
        run_started_at: timestamp de inicio (default: ahora)
        run_finished_at: timestamp de fin (default: ahora)
    """
    now = datetime.now(timezone.utc)
    log = AgentRunLog(
        agent_name=agent_name,
        status=status,
        summary=summary,
        detail=detail,
        run_started_at=run_started_at or now,
        run_finished_at=run_finished_at or now,
    )
    session.add(log)
    await session.commit()


async def fire_agent_alert(
    session: AsyncSession,
    *,
    agent_name: str,
    status: str,
    summary: str,
    detail: dict | None = None,
) -> None:
    """Envía alerta a Slack si está configurado.

    Primero persiste el resultado en agent_run_logs (siempre),
    luego intenta enviar a Slack si el webhook está configurado.
    Un fallo de Slack no tumba nada.

    Args:
        session: sesión async de BD
        agent_name: nombre del agente
        status: "ok", "warning", "critical", o "error"
        summary: descripción breve
        detail: hallazgos estructurados (opcional)
    """
    await log_agent_run(
        session,
        agent_name=agent_name,
        status=status,
        summary=summary,
        detail=detail,
    )

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.debug("No SLACK_WEBHOOK_URL configured; skipping Slack alert")
        return

    # Mapear status a emoji/color Slack
    emoji_map = {
        "ok": "✅",
        "warning": "⚠️",
        "critical": "🚨",
        "error": "❌",
    }
    color_map = {
        "ok": "#36a64f",
        "warning": "#ff9900",
        "critical": "#ff0000",
        "error": "#cc0000",
    }

    emoji = emoji_map.get(status, "ℹ️")
    color = color_map.get(status, "#808080")

    payload: dict[str, Any] = {
        "attachments": [
            {
                "fallback": f"[{agent_name}] {status.upper()}: {summary}",
                "color": color,
                "title": f"{emoji} Agent: {agent_name}",
                "text": summary,
                "mrkdwn_in": ["text"],
            }
        ]
    }

    if detail:
        detail_str = "\n".join(f"• {k}: {v}" for k, v in detail.items())
        payload["attachments"][0]["fields"] = [
            {"title": "Details", "value": detail_str, "short": False}
        ]

    result, code = await post_webhook(webhook_url, payload)
    if result != "sent":
        logger.warning("Slack alert failed for %s (status %s)", agent_name, code)
