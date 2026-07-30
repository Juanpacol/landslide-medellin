"""
Antecedent Precipitation Index (API).

Geotechnical standard for landslide risk: recent rain weighs more than old
rain because soil drains over time. Instead of a flat sum over N days, each
day is weighted with a decay factor:

    API = Σ ( rain_day_i × decay^days_back_i )

With decay=0.85, rain from 7 days ago contributes ~32% of its value and
rain from 15 days ago ~9% — the soil gradually "forgets".

The daily series comes from `rainfall_timeseries` (SIATA snapshots every 30
min, summed per day) — the same source the rain monitor and Slack alerts
use. Do NOT use `MLFeature.precip_acum_7d` (never populated).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries

DECAY_DEFAULT = 0.85
WINDOW_DAYS_DEFAULT = 15

# Key the index travels under in MLFeature's `features` JSON.
# FeatureBuilder auto-detects any new numeric key, so the model picks it up
# on retrain without a schema change.
FEATURE_KEY = "antecedent_precip_index"


def compute_antecedent_precip_index(
    daily_rain: dict[date, float],
    as_of: date,
    *,
    decay: float = DECAY_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
) -> float:
    """API over a daily series. Missing days count as 0 mm."""
    total = 0.0
    for days_back in range(window_days):
        d = as_of - timedelta(days=days_back)
        rain = daily_rain.get(d, 0.0)
        if rain > 0:
            total += rain * (decay**days_back)
    return round(total, 3)


async def antecedent_indexes_for_all_communes(
    session: AsyncSession,
    as_of: date | None = None,
    *,
    decay: float = DECAY_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
) -> dict[str, float]:
    """Index per commune in a single query (groups snapshots by commune+day)."""
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
        .group_by(
            RainfallTimeseries.commune_id,
            func.date(RainfallTimeseries.snapshot_at),
        )
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
        cid: compute_antecedent_precip_index(daily, as_of, decay=decay, window_days=window_days)
        for cid, daily in daily_by_commune.items()
    }
