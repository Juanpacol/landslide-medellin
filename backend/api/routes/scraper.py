from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
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
            }
            for r in rows
        ]
    }
