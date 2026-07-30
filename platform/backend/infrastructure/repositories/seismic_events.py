"""
Seismic repository: deduplicated insertion and grouping into canonical events.

All "are these the same earthquake?" logic lives in
`domain/seismic_dedup.py`, which is pure and testable without a database.
Only the I/O lives here.

Two things this module fixes from the previous code:

1. **N queries → 1.** `scraper/siata_sismos.py` did one `SELECT` per row to
   check if the `source_row_id` already existed. With USGS and SGC added,
   that scales badly; `existing_source_row_ids` resolves the batch in a
   single query.
2. **Cluster grouping.** Without it, each earthquake counts once per agency
   in `ml/seismic_features.py`'s Σ of magnitude², inflating it quadratically.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.seismic_event import SeismicEvent
from db.models.seismic_event_cluster import SeismicEventCluster
from domain.seismic_dedup import (
    MATCH_TIME_WINDOW_S,
    EventKey,
    best_match,
    merge_sources,
    source_rank,
)


async def existing_source_row_ids(session: AsyncSession, source_row_ids: Iterable[str]) -> set[str]:
    """Which of these `source_row_id`s already exist in the DB. ONE single query."""
    ids = [i for i in source_row_ids if i]
    if not ids:
        return set()
    stmt = select(SeismicEvent.source_row_id).where(SeismicEvent.source_row_id.in_(ids))
    return set((await session.execute(stmt)).scalars().all())


async def insert_events(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> int:
    """Inserts raw reports, ignoring ones that already exist. Returns the new ones.

    Idempotent by construction: `on_conflict_do_nothing` on the unique
    `source_row_id`. A duplicate run (cron + local scheduler at once) costs
    one row in `scraping_logs`, never duplicated data.

    Rows are normalized to a COMMON key set before inserting. Needed
    because sources are heterogeneous: SIATA carries `station_code` and
    `station_name`, USGS and SGC don't. In a multi-row INSERT, SQLAlchemy
    requires every dict to have the same keys; otherwise it fails with
    `CompileError: ... explicitly rendered as a boundparameter`, which says
    nothing about the real cause.
    """
    if not rows:
        return 0

    keys: set[str] = set()
    for row in rows:
        keys |= set(row.keys())
    normalized = [{k: row.get(k) for k in keys} for row in rows]

    stmt = (
        pg_insert(SeismicEvent)
        .values(normalized)
        .on_conflict_do_nothing(index_elements=["source_row_id"])
        .returning(SeismicEvent.id)
    )
    return len((await session.execute(stmt)).scalars().all())


def _to_key(row: SeismicEvent | SeismicEventCluster) -> EventKey:
    """Adapts a DB row to the domain's pure dataclass."""
    at = getattr(row, "event_at", None) or getattr(row, "event_local_at", None)
    return EventKey(
        event_at=at,  # type: ignore[arg-type]
        source=getattr(row, "canonical_source", None) or getattr(row, "source", ""),
        magnitude=row.magnitude,
        depth_km=row.depth_km,
        lat=row.epicenter_lat,
        lon=row.epicenter_lon,
        label=row.epicenter_label,
    )


async def _candidate_clusters(session: AsyncSession, at: datetime) -> list[SeismicEventCluster]:
    """Clusters within the matching time window (indexed on `event_at`, so
    it's a handful of rows)."""
    margin = timedelta(seconds=MATCH_TIME_WINDOW_S)
    stmt = select(SeismicEventCluster).where(
        SeismicEventCluster.event_at >= at - margin,
        SeismicEventCluster.event_at <= at + margin,
    )
    return list((await session.execute(stmt)).scalars().all())


async def assign_cluster(session: AsyncSession, event: SeismicEvent) -> int | None:
    """Assigns `event` to an existing cluster or creates one. Returns the `cluster_id`.

    Doesn't commit: the caller does, so the assignment travels in the same
    transaction as the report's insertion.

    An event with no `event_local_at` can't be grouped (time is the
    matching primary key) and is left with `cluster_id = NULL`.
    """
    if event.event_local_at is None:
        return None

    key = _to_key(event)
    candidates = await _candidate_clusters(session, event.event_local_at)
    idx = best_match(key, [_to_key(c) for c in candidates])

    if idx is None:
        cluster = SeismicEventCluster(
            event_at=event.event_local_at,
            magnitude=event.magnitude,
            mag_type=event.mag_type,
            depth_km=event.depth_km,
            epicenter_lat=event.epicenter_lat,
            epicenter_lon=event.epicenter_lon,
            epicenter_label=event.epicenter_label,
            canonical_source=event.source,
            sources=[event.source],
            source_count=1,
            member_count=1,
        )
        session.add(cluster)
        # flush (no commit) to get the generated id without closing the transaction.
        await session.flush()
        event.cluster_id = cluster.id
        return cluster.id

    cluster = candidates[idx]
    cluster.member_count = (cluster.member_count or 0) + 1
    sources = merge_sources(list(cluster.sources or []), event.source)
    cluster.sources = sources
    cluster.source_count = len(sources)

    # If the new source has MORE authority, it replaces the canonical values.
    # On a source tie, nothing is touched: reprocessing must not move consensus.
    if source_rank(event.source) < source_rank(cluster.canonical_source):
        cluster.event_at = event.event_local_at
        cluster.magnitude = event.magnitude
        cluster.mag_type = event.mag_type
        cluster.depth_km = event.depth_km
        cluster.epicenter_lat = event.epicenter_lat
        cluster.epicenter_lon = event.epicenter_lon
        cluster.epicenter_label = event.epicenter_label
        cluster.canonical_source = event.source

    event.cluster_id = cluster.id
    return cluster.id


async def recent_clusters(
    session: AsyncSession, since: datetime, *, until: datetime | None = None
) -> list[SeismicEventCluster]:
    """Canonical earthquakes with known magnitude in a window.

    This is the surface `ml/seismic_features.py` consumes: one earthquake,
    one row. Filtered by `magnitude IS NOT NULL` because intensity is a Σ
    of magnitude² and a row with no magnitude contributes nothing.
    """
    stmt = select(SeismicEventCluster).where(
        SeismicEventCluster.event_at >= since,
        SeismicEventCluster.magnitude.isnot(None),
    )
    if until is not None:
        stmt = stmt.where(SeismicEventCluster.event_at <= until)
    return list((await session.execute(stmt)).scalars().all())


async def unclustered_events(
    session: AsyncSession, *, limit: int = 1000, since: datetime | None = None
) -> list[SeismicEvent]:
    """Reports still without a cluster, in chronological order.

    Used by `scraper/seismic_cluster_backfill.py`. Order matters: grouping
    oldest to newest reproduces the order they would have arrived in.
    """
    stmt = (
        select(SeismicEvent)
        .where(
            SeismicEvent.cluster_id.is_(None),
            SeismicEvent.event_local_at.isnot(None),
        )
        .order_by(SeismicEvent.event_local_at.asc(), SeismicEvent.id.asc())
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(SeismicEvent.event_local_at >= since)
    return list((await session.execute(stmt)).scalars().all())
