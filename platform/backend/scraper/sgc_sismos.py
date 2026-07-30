"""
Colombian Geological Survey (SGC) earthquake scraper.

Replaces SIATA as the PRIMARY seismic source. Reasons measured on 2026-07-29:

- The SIATA feed hasn't produced a new event since 2026-03-01 — 150 days —
  while the scraper reports `ok` on every run, because `records_valid=0`
  means "no new events" and is indistinguishable from "the parser stopped
  matching". `monitoring/scraper_validator.py` now detects this.
- Over 7 days SGC published **35 earthquakes** within the Valle de Aburrá
  bounding box. SIATA: zero.
- USGS doesn't work as primary: over all of July 2026, with no magnitude
  threshold, it returned **0 events** in that same bbox.

Each row is grouped into a canonical event (`seismic_event_clusters`) right
after insertion, within the same transaction. Without that, the same
earthquake reported by SIATA, USGS and SGC would count three times in
`ml/seismic_features.py`'s Σ of magnitude², inflating it quadratically and
silently.

GitHub Actions entrypoint:

    cd platform/backend && PYTHONPATH=. python -m scraper.sgc_sismos
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import AsyncSessionLocal
from infrastructure.external import sgc_client
from infrastructure.repositories.seismic_events import (
    assign_cluster,
    existing_source_row_ids,
    insert_events,
)
from scraper.common import httpx_client, log_scrape_run, utcnow

logger = logging.getLogger(__name__)

SOURCE_KEY = sgc_client.SOURCE_KEY

# Query window per run. With the job every 15 min, 2 days gives a wide
# margin: covers a cron down for several hours and the late revisions SGC
# publishes (an event moves from `automatic` to `manual` and its magnitude
# changes).
LOOKBACK_DAYS = 2

# Only earthquakes worth a Slack alert. The feed carries dozens of M0.7-1.5
# events per week; posting all of them would drown the channel, exactly
# what CLAUDE.md's anti-noise rule wants to avoid.
DIGEST_MIN_MAGNITUDE = 3.0


async def _collect() -> tuple[list[dict[str, Any]], str | None]:
    """Downloads and parses. Returns (rows, detail)."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    async with httpx_client() as client:
        rows = await sgc_client.fetch_events(client, start=start, end=end + timedelta(days=1))
    return rows, f"window={start}..{end} in_bbox={len(rows)}"


async def _run_sgc_sismos(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    inserted = 0
    discarded = 0
    detail: str | None = None
    new_items: list[dict[str, Any]] = []

    try:
        rows, detail = await _collect()
        downloaded = len(rows)

        # One single query for the whole batch, instead of a SELECT per row.
        known = await existing_source_row_ids(session, [r["source_row_id"] for r in rows])
        fresh = [r for r in rows if r["source_row_id"] not in known]
        discarded = downloaded - len(fresh)

        if fresh:
            inserted = await insert_events(session, fresh)

            # Group into canonical events WITHIN the same transaction, so no
            # rows are left without a cluster if something fails afterward.
            from sqlalchemy import select

            from db.models.seismic_event import SeismicEvent

            ids = [r["source_row_id"] for r in fresh]
            stmt = select(SeismicEvent).where(SeismicEvent.source_row_id.in_(ids))
            for ev in (await session.execute(stmt)).scalars().all():
                await assign_cluster(session, ev)

            for r in sorted(fresh, key=lambda x: x["magnitude"], reverse=True):
                if r["magnitude"] >= DIGEST_MIN_MAGNITUDE:
                    new_items.append(
                        {
                            "titulo": f"Sismo M{r['magnitude']} ({r['mag_type'] or 's/d'})",
                            "detalle": (
                                f"{r['epicenter_label'] or 'epicentro s/d'} · "
                                f"profundidad {r['depth_km']} km"
                            ),
                            "fecha": str(r["event_local_at"])[:19],
                        }
                    )

        await session.commit()
        status = "ok"
        logger.info("SGC earthquakes: %d new of %d in the window", inserted, downloaded)
    except Exception as exc:  # noqa: BLE001
        detail = (detail + " | " if detail else "") + repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source=SOURCE_KEY,
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
            new_items_summary=new_items if status == "ok" else None,
        )
    return inserted


async def run_sgc_sismos_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_sgc_sismos(s)
    return await _run_sgc_sismos(session)


if __name__ == "__main__":
    from observability.logging_config import configure_logging

    configure_logging("scraper-sgc-sismos")
    asyncio.run(run_sgc_sismos_scraper())
