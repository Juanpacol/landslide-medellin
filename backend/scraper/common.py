from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.scraping_log import ScrapingLog

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 TEYVA-Scraper/1.0"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def with_retries(
    factory: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay_s: float = 1.0,
) -> T:
    delay = base_delay_s
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return await factory()
        except BaseException as exc:  # noqa: BLE001
            last = exc
            if i == attempts - 1:
                raise
            await asyncio.sleep(delay)
            delay *= 2.0
    assert last is not None
    raise last


def httpx_client(**kwargs: Any) -> httpx.AsyncClient:
    kw: dict[str, Any] = {"headers": DEFAULT_HEADERS, "timeout": 60.0, "follow_redirects": True}
    kw.update(kwargs)
    return httpx.AsyncClient(**kw)


async def log_scrape_run(
    session: AsyncSession,
    *,
    source: str,
    status: str,
    run_started_at: datetime,
    records_downloaded: int | None = None,
    records_valid: int | None = None,
    records_discarded: int | None = None,
    detail: str | None = None,
) -> None:
    log = ScrapingLog(
        source=source,
        status=status,
        run_started_at=run_started_at,
        run_finished_at=utcnow(),
        records_downloaded=records_downloaded,
        records_valid=records_valid,
        records_discarded=records_discarded,
        detail=detail,
    )
    session.add(log)
    await session.commit()


async def ml_feature_exists(
    session: AsyncSession,
    *,
    commune_id: str,
    reference_date: datetime,
    source_key: str,
) -> bool:
    stmt = select(func.count()).select_from(MLFeature).where(
        MLFeature.commune_id == commune_id,
        MLFeature.reference_date == reference_date,
        MLFeature.features["source"].as_string() == source_key,
    )
    n = await session.scalar(stmt)
    return bool(n and int(n) > 0)
