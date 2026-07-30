"""
Use case: fire the Slack alert checks at the points in the cycle where it
makes sense.

Each trigger point used to know which specific checks to run
(scraper/siata.py imported rain+snake, ml/predict.py imported
critical+yellow, the scheduler the watchdog). This module is the sole owner
of that composition: what gets checked AFTER ingesting rain, AFTER
predicting, and periodically.

Shared rule: a downed Slack never takes down the run that triggered it —
formalized via `application/orchestrator.py::run_steps`, which logs each
step separately and doesn't block the others. Positive side effect of the
refactor: `alerts_after_prediction` used to wrap critical_risk and yellow in
a SINGLE try/except — if the first failed, the second never ran. With
independent steps, each runs regardless of what happens to the other.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from application.orchestrator import Step, run_steps

logger = logging.getLogger(__name__)


async def alerts_after_rain_ingest(session: AsyncSession, commune_ids: list[str]) -> None:
    """After ingesting rain (SIATA every 30 min): daily threshold + Snake Line."""

    async def _rainfall() -> None:
        from alerts.slack import check_and_fire_alerts

        await check_and_fire_alerts(session)

    async def _snake_line() -> None:
        from alerts.snake_line import check_and_fire_snake_line_alerts

        await check_and_fire_snake_line_alerts(session, commune_ids)

    await run_steps(
        [
            Step("rainfall_threshold", _rainfall),
            Step("snake_line", _snake_line),
        ]
    )


async def alerts_after_prediction(session: AsyncSession) -> None:
    """After writing new predictions: critical risk + Yellow state."""

    async def _critical_risk() -> None:
        from alerts.slack import check_and_fire_critical_risk_alerts

        await check_and_fire_critical_risk_alerts(session)

    async def _yellow() -> None:
        from alerts.slack import check_and_fire_yellow_alerts

        await check_and_fire_yellow_alerts(session)

    await run_steps(
        [
            Step("critical_risk_alerts", _critical_risk),
            Step("yellow_alerts", _yellow),
        ]
    )


async def alerts_scraper_watchdog(session: AsyncSession) -> list[str]:
    """Periodic (scheduler every 30 min): downed or silent scrapers."""
    try:
        from alerts.slack import check_and_fire_scraper_alerts

        return await check_and_fire_scraper_alerts(session)
    except Exception:  # noqa: BLE001
        logger.exception("Scraper watchdog failed (non-critical)")
        return []
