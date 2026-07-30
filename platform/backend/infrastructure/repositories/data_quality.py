"""Real-time quality-flag computation for the inference path.

Reuses the same plausibility predicates `monitoring/scraper_validator.py` applies in its
periodic batch job (`domain/quality.py`), but runs synchronously inside `infer_all` so
`TerritorySnapshot.quality_flags` reflects the current run's data instead of a finding logged
separately, out-of-band, in `agent_run_logs` that the rule engine never sees.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.seismic_event import SeismicEvent
from domain.quality import (
    MIN_ROWS_FOR_DISTINCT_CHECK,
    SEISMIC_STALE_DAYS,
    is_frozen_signal,
    is_implausibly_low_max,
    is_stale,
)

PLAUSIBILITY_WINDOW_DAYS = 14


async def current_quality_flags(session: AsyncSession) -> frozenset[str]:
    """City-wide data-quality flags for THIS run: frozen rain signal, implausibly low rain
    max over a long window, or a stale seismic feed.

    Applied uniformly to every commune's `TerritorySnapshot`: these are network-wide symptoms
    (audit finding 2, docs/research/audit-2026-07.md — the SIATA aggregation bug affected all
    21 communes identically), not per-commune ones.
    """
    flags: set[str] = set()
    now = datetime.now(timezone.utc)

    rain_rows = (
        await session.scalars(
            select(RainfallTimeseries.precip_mm)
            .order_by(RainfallTimeseries.snapshot_at.desc())
            .limit(1000)
        )
    ).all()
    if is_frozen_signal(list(rain_rows), min_rows=MIN_ROWS_FOR_DISTINCT_CHECK):
        flags.add("frozen_rain_signal")

    cutoff = now - timedelta(days=PLAUSIBILITY_WINDOW_DAYS)
    max_mm, n_window = (
        await session.execute(
            select(func.max(RainfallTimeseries.precip_mm), func.count()).where(
                RainfallTimeseries.snapshot_at >= cutoff
            )
        )
    ).one()
    if is_implausibly_low_max(window_max_mm=max_mm or 0.0, window_rows=n_window or 0):
        flags.add("implausible_rain_max")

    latest_seismic = (await session.execute(select(func.max(SeismicEvent.event_local_at)))).scalar()
    if latest_seismic is not None:
        days = (now - latest_seismic).days
        if is_stale(days, threshold_days=SEISMIC_STALE_DAYS):
            flags.add("stale_seismic_feed")

    return frozenset(flags)
