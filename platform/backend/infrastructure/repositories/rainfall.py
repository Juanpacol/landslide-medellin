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
    """Lluvia acumulada por comuna desde `since` (típicamente medianoche local).

    Suma TODAS las fuentes de `rainfall_timeseries` sin filtrar, y eso es correcto
    solo porque se apoya en dos invariantes que se garantizan al ESCRIBIR:

    1. El pronóstico nunca entra en esta tabla (vive en `rainfall_forecast`). Si
       entrara, esta suma inflaría el acumulado del día y dispararía alertas
       Slack rojas falsas — este resultado alimenta `alerts_after_rain_ingest`.
    2. `owm_observed` solo se escribe para un (comuna, día) que NO tenga ya filas
       de SIATA. Sin esa compuerta, un total diario de OWM se sumaría a los ~48
       snapshots de SIATA del mismo día y contaría la lluvia dos veces.

    Si algún día hace falta relajar el punto 2, esta función necesita un filtro
    por `source` y una escalera de precedencia — que es justo lo que hace
    `infrastructure/repositories/daily_rain.py` para el grano diario.
    """
    result = await session.execute(
        select(RainfallTimeseries.commune_id, func.sum(RainfallTimeseries.precip_mm))
        .where(RainfallTimeseries.snapshot_at >= since)
        .group_by(RainfallTimeseries.commune_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}
