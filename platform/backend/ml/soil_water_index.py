"""
Soil Water Index (SWI) — estimated soil saturation, not just fallen rain.

JMA methodology (Japan Meteorological Agency): instead of measuring
instantaneous rain in millimeters, it models how much water stays retained
"inside" the slope with a simplified tank (one layer, a reduced version of
the 3-layer Sugawara tank model Japan uses):

    SWI(t) = SWI(t-1) * (1 - drain_rate) + rain(t)   [capped to 0-100]

- drain_rate=0.15/day: conservative literature value for clay soil (typical
  of Medellín's hillsides) — an explicit MVP, not yet calibrated against
  real, precisely-timestamped historical landslide events.
- Why it matters: it detects risk AFTER the rain stops (SWI stays high for
  several days) and distinguishes a downpour on dry soil (drains fast) from
  one on already-saturated soil (high SWI, more dangerous).

Same source as `ml/precip_index.py` (RainfallTimeseries, SIATA every 30
min) — reuses the same module pattern.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries

DRAIN_RATE_DEFAULT = 0.15
SATURATION_CAP = 100.0
WINDOW_DAYS_DEFAULT = 30  # enough history for the tank to "forget" the initial state

# Key the index travels under in MLFeature's `features` JSON.
FEATURE_KEY = "soil_water_index_pct"


def compute_swi(
    daily_rain: dict[date, float],
    as_of: date,
    *,
    drain_rate: float = DRAIN_RATE_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
    cap: float = SATURATION_CAP,
) -> float:
    """SWI as a % of saturation (0-100), simulating the tank day by day from
    `window_days` back up to `as_of`. Days with no telemetry count as 0 mm
    of rain (the tank keeps draining)."""
    swi = 0.0
    start = as_of - timedelta(days=window_days - 1)
    for i in range(window_days):
        d = start + timedelta(days=i)
        swi = swi * (1 - drain_rate)
        swi += daily_rain.get(d, 0.0)
        swi = min(swi, cap)
    return round(swi, 2)


async def swi_for_all_communes(
    session: AsyncSession,
    as_of: date | None = None,
    *,
    drain_rate: float = DRAIN_RATE_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
) -> dict[str, float]:
    """Current SWI per commune (same daily aggregation as
    `ml/precip_index.py::antecedent_indexes_for_all_communes`)."""
    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    start_dt = datetime.combine(
        as_of - timedelta(days=window_days - 1), time.min, tzinfo=timezone.utc
    )

    stmt = (
        select(
            RainfallTimeseries.commune_id,
            func.date(RainfallTimeseries.snapshot_at),
            func.sum(RainfallTimeseries.precip_mm),
        )
        .where(RainfallTimeseries.snapshot_at >= start_dt)
        .group_by(RainfallTimeseries.commune_id, func.date(RainfallTimeseries.snapshot_at))
    )

    daily_by_commune: dict[str, dict[date, float]] = {}
    for commune_id, day_value, total in (await session.execute(stmt)).all():
        d = (
            day_value
            if isinstance(day_value, date)
            else datetime.fromisoformat(str(day_value)).date()
        )
        daily_by_commune.setdefault(str(commune_id), {})[d] = float(total or 0.0)

    return {
        cid: compute_swi(daily, as_of, drain_rate=drain_rate, window_days=window_days)
        for cid, daily in daily_by_commune.items()
    }
