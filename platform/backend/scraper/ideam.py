from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from scraper.commune import lookup_commune_for_point
from scraper.common import httpx_client, log_scrape_run, ml_feature_exists, utcnow, with_retries

SOCRATA_BASE = "https://www.datos.gov.co/resource/57sv-p2fu.json"


def _parse_obs_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _collect_ideam_rows() -> tuple[list[dict[str, Any]], int]:
    where = "descripcionsensor like '%PRECIP%' and upper(municipio) like '%MEDELL%'"
    limit = 5000
    offset = 0
    rows: list[dict[str, Any]] = []
    async with httpx_client() as client:
        while True:

            async def _page(off: int):
                async def _call():
                    params = {"$where": where, "$limit": str(limit), "$offset": str(off)}
                    r = await client.get(SOCRATA_BASE, params=params)
                    r.raise_for_status()
                    return r.json()

                return await with_retries(_call)

            batch = await _page(offset)
            if not isinstance(batch, list) or not batch:
                break
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            if offset > 20000:
                break
    return rows, len(rows)


async def _aggregate_ideam(rows: list[dict[str, Any]]) -> dict[tuple[str, datetime], tuple[list[float], list[str]]]:
    by_commune_day: dict[tuple[str, datetime], list[float]] = defaultdict(list)
    station_meta: dict[tuple[str, datetime], list[str]] = defaultdict(list)
    cache: dict[tuple[int, int], str | None] = {}
    dedupe_station_day: set[tuple[str, str]] = set()

    async with httpx_client() as client:
        for row in rows:
            try:
                lon = float(row.get("longitud"))
                lat = float(row.get("latitud"))
                val = float(row.get("valorobservado") or 0)
            except (TypeError, ValueError):
                continue
            obs = _parse_obs_dt(row.get("fechaobservacion"))
            if obs is None:
                continue
            obs = obs.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            st_code = str(row.get("codigoestacion") or "")
            day_key = obs.date().isoformat()
            sd_key = (st_code, day_key)
            if sd_key in dedupe_station_day:
                continue
            dedupe_station_day.add(sd_key)

            key = (round(lat, 3), round(lon, 3))
            if key not in cache:
                info = await lookup_commune_for_point(client, lon, lat)
                cache[key] = info.get("ml_commune_id")
            cid = cache[key]
            if not cid:
                continue
            by_commune_day[(cid, obs)].append(val)
            station_meta[(cid, obs)].append(st_code)

    return {k: (v, station_meta[k]) for k, v in by_commune_day.items()}


async def _run_ideam(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    discarded = 0
    inserted = 0
    detail: str | None = None
    try:
        rows, downloaded = await _collect_ideam_rows()
        aggregated = await _aggregate_ideam(rows)

        for (cid, day), (vals, codes) in aggregated.items():
            exists = await ml_feature_exists(
                session, commune_id=cid, reference_date=day, source_key="ideam"
            )
            if exists:
                discarded += 1
                continue
            total = sum(vals)
            feats = {
                "source": "ideam",
                "socrata_dataset": "57sv-p2fu",
                "station_codes": sorted({c for c in codes if c})[:40],
                "precip_records": len(vals),
                "precip_sum_mm_day": round(total, 3),
            }
            session.add(
                MLFeature(
                    commune_id=cid,
                    reference_date=day,
                    features=feats,
                    precip_acum_7d=None,
                    n_events_window=None,
                )
            )
            inserted += 1
        await session.commit()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        detail = repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source="ideam",
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
        )
    return inserted


async def run_ideam_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_ideam(s)
    return await _run_ideam(session)


async def main():
    n = await run_ideam_scraper()
    print("ideam_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
