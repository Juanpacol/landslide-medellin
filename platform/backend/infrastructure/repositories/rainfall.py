"""
Repositorio de lluvia y umbrales — queries compartidas entre las alertas
Slack (alerts/slack.py) y el monitor de lluvia (api/routes/rain.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.commune_threshold import CommuneThreshold
from db.models.rainfall_timeseries import RainfallTimeseries

DEFAULT_THRESHOLD_MM = 35.0


async def thresholds_by_commune(session: AsyncSession) -> dict[str, float]:
    """Umbral diario configurado por comuna (sin default: el caller decide
    qué hacer con las comunas sin fila — DEFAULT_THRESHOLD_MM)."""
    result = await session.execute(select(CommuneThreshold))
    return {r.commune_id: r.threshold_mm for r in result.scalars().all()}


async def accumulated_since_by_commune(session: AsyncSession, since: datetime) -> dict[str, float]:
    """Lluvia acumulada por comuna desde `since` (típicamente medianoche local)."""
    result = await session.execute(
        select(RainfallTimeseries.commune_id, func.sum(RainfallTimeseries.precip_mm))
        .where(RainfallTimeseries.snapshot_at >= since)
        .group_by(RainfallTimeseries.commune_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}
