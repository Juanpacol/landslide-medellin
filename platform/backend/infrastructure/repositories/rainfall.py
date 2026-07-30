"""
Rainfall and threshold repository — queries shared between Slack alerts
(alerts/slack.py) and the rain monitor (api/routes/rain.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.commune_threshold import CommuneThreshold
from db.models.rainfall_timeseries import RainfallTimeseries

DEFAULT_THRESHOLD_MM = 35.0


async def thresholds_by_commune(session: AsyncSession) -> dict[str, float]:
    """Daily threshold configured per commune (no default: the caller
    decides what to do with communes without a row — DEFAULT_THRESHOLD_MM)."""
    result = await session.execute(select(CommuneThreshold))
    return {r.commune_id: r.threshold_mm for r in result.scalars().all()}


async def accumulated_since_by_commune(session: AsyncSession, since: datetime) -> dict[str, float]:
    """Accumulated rain per commune since `since` (typically local midnight).

    Sums ALL sources in `rainfall_timeseries` unfiltered, and that's only
    correct because it relies on two invariants guaranteed at WRITE time:

    1. The forecast never enters this table (it lives in
       `rainfall_forecast`). If it did, this sum would inflate the day's
       accumulation and fire false red Slack alerts — this result feeds
       `alerts_after_rain_ingest`.
    2. `owm_observed` is only written for a (commune, day) that does NOT
       already have SIATA rows. Without that gate, an OWM daily total would
       get added to the same day's ~48 SIATA snapshots and double-count the
       rain.

    If relaxing point 2 is ever needed, this function needs a `source`
    filter and a precedence ladder — exactly what
    `infrastructure/repositories/daily_rain.py` does for the daily grain.
    """
    result = await session.execute(
        select(RainfallTimeseries.commune_id, func.sum(RainfallTimeseries.precip_mm))
        .where(RainfallTimeseries.snapshot_at >= since)
        .group_by(RainfallTimeseries.commune_id)
    )
    return {row[0]: float(row[1]) for row in result.all()}
