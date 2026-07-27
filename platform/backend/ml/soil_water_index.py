"""
Soil Water Index (SWI) — saturación estimada del suelo, no solo lluvia caída.

Metodología JMA (Agencia Meteorológica de Japón): en vez de medir milímetros
de lluvia instantánea, se modela cuánta agua queda retenida "dentro" de la
ladera con un tanque simplificado (una capa, versión reducida del modelo de
tanques de Sugawara de 3 capas que usa Japón):

    SWI(t) = SWI(t-1) * (1 - drain_rate) + lluvia(t)   [capado a 0-100]

- drain_rate=0.15/día: valor conservador de literatura para suelo arcilloso
  (típico de laderas de Medellín) — MVP explícito, sin calibrar todavía con
  eventos históricos reales de deslizamiento con timestamp preciso.
- Por qué importa: permite detectar riesgo DESPUÉS de que para de llover
  (SWI sigue alto varios días) y distinguir un aguacero sobre suelo seco
  (drena rápido) de uno sobre suelo ya saturado (SWI alto, más peligroso).

Misma fuente que `ml/precip_index.py` (RainfallTimeseries, SIATA cada 30 min)
— reutiliza el mismo patrón de módulo.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries

DRAIN_RATE_DEFAULT = 0.15
SATURATION_CAP = 100.0
WINDOW_DAYS_DEFAULT = 30  # historial suficiente para que el tanque "olvide" el estado inicial

# Clave con la que el índice viaja en el JSON `features` de MLFeature.
FEATURE_KEY = "soil_water_index_pct"


def compute_swi(
    daily_rain: dict[date, float],
    as_of: date,
    *,
    drain_rate: float = DRAIN_RATE_DEFAULT,
    window_days: int = WINDOW_DAYS_DEFAULT,
    cap: float = SATURATION_CAP,
) -> float:
    """SWI en % de saturación (0-100), simulando el tanque día a día desde
    `window_days` atrás hasta `as_of`. Días sin telemetría cuentan como 0 mm
    de lluvia (el tanque sigue drenando)."""
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
    """SWI actual por comuna (misma agregación por día que
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
