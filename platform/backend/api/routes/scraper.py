from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from constants import SCRAPER_INTERVALS_MIN as SCRAPER_INTERVALS
from db.models import ScrapingLog
from db.session import get_async_db
from domain.validation import FAILURE_STATUSES as _FAILURE_STATUSES
from domain.validation import SUCCESS_STATUSES as _SUCCESS_STATUSES
from domain.validation import validate_scrape_log_status

router = APIRouter()


class ScraperRunBody(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="started", max_length=32)
    detail: str | None = Field(default=None, max_length=4000)


@router.post("/log")
async def create_scrape_log(body: ScraperRunBody, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    status = validate_scrape_log_status(body.status)
    now = datetime.now(timezone.utc)
    row = ScrapingLog(
        source=body.source,
        status=status,
        run_started_at=now,
        detail=body.detail,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "source": row.source, "status": row.status}


@router.get("/logs")
async def list_logs(limit: int = 30, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    stmt = select(ScrapingLog).order_by(ScrapingLog.created_at.desc()).limit(min(limit, 100))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "source": r.source,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "records_downloaded": r.records_downloaded,
                "records_valid": r.records_valid,
                "records_discarded": r.records_discarded,
                "run_started_at": r.run_started_at.isoformat() if r.run_started_at else None,
                "run_finished_at": r.run_finished_at.isoformat() if r.run_finished_at else None,
            }
            for r in rows
        ]
    }


@router.get("/status")
async def scraper_status(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    latest_rows = (
        await db.execute(
            select(ScrapingLog)
            .order_by(ScrapingLog.created_at.desc())
            .limit(200)
        )
    ).scalars().all()

    by_source: dict[str, ScrapingLog] = {}
    for row in latest_rows:
        if row.source not in by_source:
            by_source[row.source] = row

    sources = []
    for source, row in sorted(by_source.items()):
        sources.append(
            {
                "source": source,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "records_downloaded": row.records_downloaded,
                "records_valid": row.records_valid,
                "records_discarded": row.records_discarded,
                "run_started_at": row.run_started_at.isoformat() if row.run_started_at else None,
                "run_finished_at": row.run_finished_at.isoformat() if row.run_finished_at else None,
            }
        )

    totals = await db.execute(
        select(
            func.count(ScrapingLog.id),
            func.coalesce(func.sum(ScrapingLog.records_downloaded), 0),
            func.coalesce(func.sum(ScrapingLog.records_valid), 0),
            func.coalesce(func.sum(ScrapingLog.records_discarded), 0),
        )
    )
    total_runs, total_downloaded, total_valid, total_discarded = totals.one()

    return {
        "summary": {
            "total_runs": int(total_runs or 0),
            "records_downloaded": int(total_downloaded or 0),
            "records_valid": int(total_valid or 0),
            "records_discarded": int(total_discarded or 0),
        },
        "sources": sources,
    }


@router.get("/health")
async def scraper_health(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Per-source health computed on-demand from scraping_logs."""
    stmt = select(ScrapingLog).order_by(ScrapingLog.run_started_at.desc()).limit(500)
    result = await db.execute(stmt)
    all_rows = result.scalars().all()

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    by_source: dict[str, list[ScrapingLog]] = {}
    for row in all_rows:
        if row.source not in by_source:
            by_source[row.source] = []
        by_source[row.source].append(row)

    for source in SCRAPER_INTERVALS:
        if source not in by_source:
            by_source[source] = []

    sources_health: list[dict[str, Any]] = []
    for source in sorted(by_source):
        rows = by_source[source]
        interval_min = SCRAPER_INTERVALS.get(source, 60)

        # Count consecutive failures from the most-recent run backwards
        consecutive_failures = 0
        for row in rows:
            if row.status in _FAILURE_STATUSES:
                consecutive_failures += 1
            elif row.status != "started":
                break

        # Most recent successful run
        last_success = next(
            (r for r in rows if r.status in _SUCCESS_STATUSES), None
        )
        last_success_at: datetime | None = None
        if last_success:
            ts = last_success.run_finished_at or last_success.run_started_at
            last_success_at = ts.replace(tzinfo=timezone.utc) if ts and ts.tzinfo is None else ts

        data_lag_minutes: int | None = None
        if last_success_at:
            data_lag_minutes = int((now - last_success_at).total_seconds() / 60)

        # 24-h success rate (ignore "started" rows that haven't finished yet)
        rows_24h = [
            r for r in rows
            if r.run_started_at
            and (r.run_started_at.replace(tzinfo=timezone.utc) if r.run_started_at.tzinfo is None else r.run_started_at) >= cutoff_24h
            and r.status != "started"
        ]
        success_rate_24h: float | None = None
        if rows_24h:
            successes = sum(1 for r in rows_24h if r.status in _SUCCESS_STATUSES)
            success_rate_24h = round(successes / len(rows_24h) * 100, 1)

        # Status classification
        if not rows:
            status = "unknown"
        elif consecutive_failures >= 3 or (data_lag_minutes is not None and data_lag_minutes > interval_min * 3):
            status = "critical"
        elif consecutive_failures >= 1 or (data_lag_minutes is not None and data_lag_minutes > interval_min * 2):
            status = "warning"
        else:
            status = "healthy"

        last_row = rows[0] if rows else None
        last_started = last_row.run_started_at if last_row else None
        if last_started and last_started.tzinfo is None:
            last_started = last_started.replace(tzinfo=timezone.utc)

        sources_health.append({
            "source": source,
            "status": status,
            "last_success_at": last_success_at.isoformat() if last_success_at else None,
            "consecutive_failures": consecutive_failures,
            "success_rate_24h": success_rate_24h,
            "data_lag_minutes": data_lag_minutes,
            "interval_minutes": interval_min,
            "total_runs_24h": len(rows_24h),
            "last_run_status": last_row.status if last_row else None,
            "last_run_at": last_started.isoformat() if last_started else None,
            "last_records_valid": last_row.records_valid if last_row else None,
            "last_detail": last_row.detail if last_row else None,
        })

    statuses = {s["status"] for s in sources_health}
    if "critical" in statuses:
        overall = "critical"
    elif "warning" in statuses or "unknown" in statuses:
        overall = "warning"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "sources": sources_health,
        "computed_at": now.isoformat(),
    }


@router.get("/timeline")
async def scraper_timeline(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Last 20 runs per source, newest-first — for timeline chart."""
    stmt = select(ScrapingLog).order_by(ScrapingLog.run_started_at.desc()).limit(400)
    result = await db.execute(stmt)
    all_rows = result.scalars().all()

    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        if row.source not in by_source:
            by_source[row.source] = []
        if len(by_source[row.source]) < 20:
            started = row.run_started_at
            finished = row.run_finished_at
            if started and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if finished and finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            by_source[row.source].append({
                "id": row.id,
                "status": row.status,
                "run_started_at": started.isoformat() if started else None,
                "run_finished_at": finished.isoformat() if finished else None,
                "records_downloaded": row.records_downloaded,
                "records_valid": row.records_valid,
                "detail": row.detail,
            })

    for source in SCRAPER_INTERVALS:
        if source not in by_source:
            by_source[source] = []

    return {"sources": {s: runs for s, runs in sorted(by_source.items())}}
