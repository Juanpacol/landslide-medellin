from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ScrapingLog
from db.session import get_async_db

router = APIRouter()


class ScraperRunBody(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="started", max_length=32)
    detail: str | None = Field(default=None, max_length=4000)


@router.post("/log")
async def create_scrape_log(body: ScraperRunBody, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    row = ScrapingLog(
        source=body.source,
        status=body.status,
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
