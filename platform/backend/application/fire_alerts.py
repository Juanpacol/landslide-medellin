"""
Caso de uso: disparar los checks de alertas Slack en los puntos del ciclo
donde tiene sentido.

Antes cada punto de disparo conocía qué checks concretos correr
(scraper/siata.py importaba rain+snake, ml/predict.py importaba
critical+yellow, el scheduler el watchdog). Este módulo es el único dueño
de esa composición: qué se chequea DESPUÉS de ingerir lluvia, DESPUÉS de
predecir, y periódicamente.

Regla compartida: un Slack caído nunca tumba la corrida que lo disparó —
todos los checks van envueltos y solo loggean.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def alerts_after_rain_ingest(session: AsyncSession, commune_ids: list[str]) -> None:
    """Tras ingerir lluvia (SIATA cada 30 min): umbral diario + Snake Line."""
    try:
        from alerts.slack import check_and_fire_alerts

        await check_and_fire_alerts(session)
    except Exception:  # noqa: BLE001
        logger.exception("Check de alertas de lluvia falló (no crítico)")

    try:
        from alerts.snake_line import check_and_fire_snake_line_alerts

        await check_and_fire_snake_line_alerts(session, commune_ids)
    except Exception:  # noqa: BLE001
        logger.exception("Check de Snake Line falló (no crítico)")


async def alerts_after_prediction(session: AsyncSession) -> None:
    """Tras escribir predicciones nuevas: riesgo crítico + estado Amarillo."""
    try:
        from alerts.slack import check_and_fire_critical_risk_alerts, check_and_fire_yellow_alerts

        await check_and_fire_critical_risk_alerts(session)
        await check_and_fire_yellow_alerts(session)
    except Exception:  # noqa: BLE001
        logger.exception("Alertas Slack post-predicción fallaron (no crítico)")


async def alerts_scraper_watchdog(session: AsyncSession) -> list[str]:
    """Periódico (scheduler cada 30 min): scrapers caídos o silenciosos."""
    try:
        from alerts.slack import check_and_fire_scraper_alerts

        return await check_and_fire_scraper_alerts(session)
    except Exception:  # noqa: BLE001
        logger.exception("Watchdog de scrapers falló (no crítico)")
        return []
