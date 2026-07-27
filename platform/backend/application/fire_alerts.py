"""
Caso de uso: disparar los checks de alertas Slack en los puntos del ciclo
donde tiene sentido.

Antes cada punto de disparo conocía qué checks concretos correr
(scraper/siata.py importaba rain+snake, ml/predict.py importaba
critical+yellow, el scheduler el watchdog). Este módulo es el único dueño
de esa composición: qué se chequea DESPUÉS de ingerir lluvia, DESPUÉS de
predecir, y periódicamente.

Regla compartida: un Slack caído nunca tumba la corrida que lo disparó — se
formaliza con `application/orchestrator.py::run_steps`, que loggea cada paso
por separado y no bloquea a los demás. Efecto colateral positivo del
refactor: antes `alerts_after_prediction` envolvía critical_risk y yellow en
un ÚNICO try/except — si el primero fallaba, el segundo nunca corría. Con
pasos independientes, cada uno corre pase lo que pase con el otro.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from application.orchestrator import Step, run_steps

logger = logging.getLogger(__name__)


async def alerts_after_rain_ingest(session: AsyncSession, commune_ids: list[str]) -> None:
    """Tras ingerir lluvia (SIATA cada 30 min): umbral diario + Snake Line."""

    async def _rainfall() -> None:
        from alerts.slack import check_and_fire_alerts

        await check_and_fire_alerts(session)

    async def _snake_line() -> None:
        from alerts.snake_line import check_and_fire_snake_line_alerts

        await check_and_fire_snake_line_alerts(session, commune_ids)

    await run_steps([
        Step("rainfall_threshold", _rainfall),
        Step("snake_line", _snake_line),
    ])


async def alerts_after_prediction(session: AsyncSession) -> None:
    """Tras escribir predicciones nuevas: riesgo crítico + estado Amarillo."""

    async def _critical_risk() -> None:
        from alerts.slack import check_and_fire_critical_risk_alerts

        await check_and_fire_critical_risk_alerts(session)

    async def _yellow() -> None:
        from alerts.slack import check_and_fire_yellow_alerts

        await check_and_fire_yellow_alerts(session)

    await run_steps([
        Step("critical_risk_alerts", _critical_risk),
        Step("yellow_alerts", _yellow),
    ])


async def alerts_scraper_watchdog(session: AsyncSession) -> list[str]:
    """Periódico (scheduler cada 30 min): scrapers caídos o silenciosos."""
    try:
        from alerts.slack import check_and_fire_scraper_alerts

        return await check_and_fire_scraper_alerts(session)
    except Exception:  # noqa: BLE001
        logger.exception("Watchdog de scrapers falló (no crítico)")
        return []
