"""
Slack HTTP client (Incoming Webhooks) — pure transport.

Payload CONSTRUCTION (blocks, colors, cooldowns) stays in alerts/slack.py
and alerts/snake_line.py; only the POST lives here.
"""

from __future__ import annotations

import logging

import httpx

from errors.error_handler import TransientError, retry_transient_call

logger = logging.getLogger(__name__)


async def post_webhook(
    webhook_url: str, payload: dict, *, retries: int = 3, base_delay_s: float = 1.0
) -> tuple[str, int | None]:
    """POST to the webhook. Returns ("sent"|"failed", status_code|None).
    Never raises: a downed Slack must not take down alerts or predictions.

    The retry lives HERE, not at each of alerts/slack.py's call sites: this
    function owns the "never raises, always returns (status, code)"
    contract; if the retry lived outside, each of the ~4 call sites would
    have to reimplement the swallow-never-throw, risking someone forgetting
    it. Only 5xx (failure on Slack's side) retries — a 4xx (invalid payload
    or revoked webhook) isn't fixed by retrying.
    """

    async def _attempt() -> tuple[str, int | None]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(webhook_url, json=payload)
        if r.status_code == 200:
            return "sent", r.status_code
        if 500 <= r.status_code < 600:
            raise TransientError(f"Slack responded {r.status_code}")
        return "failed", r.status_code

    try:
        return await retry_transient_call(
            _attempt,
            attempts=retries,
            base_delay_s=base_delay_s,
            exceptions=(TransientError, httpx.TimeoutException, httpx.ConnectError),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack webhook error after retries: %s", exc)
        return "failed", None
