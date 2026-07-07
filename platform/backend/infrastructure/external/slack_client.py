"""
Cliente HTTP de Slack (Incoming Webhooks) — transporte puro.

La CONSTRUCCIÓN de payloads (bloques, colores, cooldowns) sigue en
alerts/slack.py y alerts/snake_line.py; aquí solo vive el POST.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def post_webhook(webhook_url: str, payload: dict) -> tuple[str, int | None]:
    """POST al webhook. Devuelve ("sent"|"failed", status_code|None).
    Nunca lanza: un Slack caído no debe tumbar alertas ni predicciones."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook_url, json=payload)
            return ("sent" if r.status_code == 200 else "failed"), r.status_code
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack webhook error: %s", exc)
        return "failed", None
