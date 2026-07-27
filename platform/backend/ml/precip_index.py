"""
Índice de Precipitación Antecedente (API, Antecedent Precipitation Index).

Estándar geotécnico para riesgo de deslizamientos: la lluvia reciente pesa
más que la antigua porque el suelo drena con el tiempo. En vez de la suma
plana de N días, se pondera cada día con un factor de decaimiento:

    API = Σ ( lluvia_día_i × decay^días_atrás_i )

Con decay=0.85 la lluvia de hace 7 días aporta ~32% de su valor y la de
hace 15 días ~9% — el suelo "olvida" gradualmente.

La serie diaria sale de `rainfall_timeseries` (snapshots SIATA cada 30 min,
sumados por día) — la misma fuente que usa el monitor de lluvia y las
alertas de Slack. NO usar `MLFeature.precip_acum_7d` (nunca se llena).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries

DECAY_DEFAULT = 0.85
WINDOW_DAYS_DEFAULT = 15

# Clave con la que el índice viaja en el JSON `features` de MLFeature.
# FeatureBuilder auto-detecta cualquier clave numérica nueva, así que el
# modelo la incorpora al reentrenar sin cambios de esquema.
FEATURE_KEY = "antecedent_precip_index"


def compute_antecedent_precip_index(
    daily_rain: dict[date, float],
    as_of: date,
    *,
    decay: float = DECAY_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
) -> float:
    """API sobre una serie diaria. Días ausentes cuentan como 0 mm."""
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
    """Índice por comuna en una sola query (agrupa snapshots por comuna+día)."""
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
