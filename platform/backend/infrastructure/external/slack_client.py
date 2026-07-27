"""
Cliente HTTP de Slack (Incoming Webhooks) — transporte puro.

La CONSTRUCCIÓN de payloads (bloques, colores, cooldowns) sigue en
alerts/slack.py y alerts/snake_line.py; aquí solo vive el POST.
"""

from __future__ import annotations

import logging

import httpx

from errors.error_handler import TransientError, retry_transient_call

logger = logging.getLogger(__name__)


async def post_webhook(
    webhook_url: str, payload: dict, *, retries: int = 3, base_delay_s: float = 1.0
) -> tuple[str, int | None]:
    """POST al webhook. Devuelve ("sent"|"failed", status_code|None).
    Nunca lanza: un Slack caído no debe tumbar alertas ni predicciones.

    El retry vive AQUÍ, no en cada call-site de alerts/slack.py: esta función
    es dueña del contrato "nunca lanza, siempre devuelve (status, code)"; si
    el retry viviera afuera, cada uno de los ~4 call-sites tendría que
    reimplementar el swallow-never-throw, con riesgo de que alguien lo olvide.
    Solo los 5xx (falla del lado de Slack) reintentan — un 4xx (payload
    inválido o webhook revocado) no se arregla reintentando.
    """

    async def _attempt() -> tuple[str, int | None]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook_url, json=payload)
        if r.status_code == 200:
            return "sent", r.status_code
        if 500 <= r.status_code < 600:
            raise TransientError(f"Slack respondió {r.status_code}")
        return "failed", r.status_code

    try:
        return await retry_transient_call(
            _attempt,
            attempts=retries,
            base_delay_s=base_delay_s,
            exceptions=(TransientError, httpx.TimeoutException, httpx.ConnectError),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack webhook error tras reintentos: %s", exc)
        return "failed", None
