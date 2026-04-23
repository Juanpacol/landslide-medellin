from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from scraper.commune import lookup_commune_for_point, parse_ml_commune_from_siata_field
from scraper.common import httpx_client, log_scrape_run, ml_feature_exists, utcnow, with_retries

SIATA_HOME = "https://www.siata.gov.co"
PLUVIO_JSON = "https://siata.gov.co/data/siata_app/Pluviometrica.json"


def _floor_minute_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)


async def _fetch_siata_home_html(client) -> str | None:
    async def _call():
        r = await client.get(SIATA_HOME)
        if r.status_code == 403:
            return None
        r.raise_for_status()
        return r.text

    try:
        return await with_retries(_call)
    except Exception:
        return None


async def _fetch_pluvio(client) -> dict[str, Any]:
    async def _call():
        r = await client.get(PLUVIO_JSON)
        r.raise_for_status()
        return r.json()

    return await with_retries(_call)


async def _collect_siata_payload() -> (
    tuple[dict[str, list[float]], dict[str, dict[str, Any]], datetime, str | None, int]
):
    detail: str | None = None
    async with httpx_client() as client:
        html = await _fetch_siata_home_html(client)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
            detail = f"home_links={len(links)}"
        data = await _fetch_pluvio(client)
        stations = data.get("estaciones") or []
        raw_count = len(stations)
        ref_dt = _floor_minute_utc(utcnow())

        by_commune: dict[str, list[float]] = defaultdict(list)
        meta: dict[str, dict[str, Any]] = {}
        cache: dict[tuple[int, int], str | None] = {}

        for st in stations:
            try:
                val = float(st.get("valor"))
            except (TypeError, ValueError):
                continue
            if val <= -900:
                continue
            lat = float(st.get("latitud"))
            lon = float(st.get("longitud"))
            key = (round(lat, 4), round(lon, 4))
            ml_id = None
            comuna_txt = (st.get("comuna") or "").strip()
            if comuna_txt:
                ml_id = parse_ml_commune_from_siata_field(comuna_txt)
            if ml_id is None:
                if key not in cache:
                    info = await lookup_commune_for_point(client, lon, lat)
                    cache[key] = info.get("ml_commune_id")
                ml_id = cache[key]
            if not ml_id:
                continue
            by_commune[ml_id].append(val)
            if ml_id not in meta:
                meta[ml_id] = {"station_codes": [], "barrios": set()}
            meta[ml_id]["station_codes"].append(st.get("codigo"))
            if st.get("barrio"):
                meta[ml_id]["barrios"].add(str(st.get("barrio")))

    return by_commune, meta, ref_dt, detail, raw_count


async def _run_siata(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    discarded = 0
    inserted = 0
    detail: str | None = None
    try:
        by_commune, meta, ref_dt, detail, downloaded = await _collect_siata_payload()

        for cid, values in by_commune.items():
            exists = await ml_feature_exists(
                session, commune_id=cid, reference_date=ref_dt, source_key="siata"
            )
            if exists:
                discarded += 1
                continue
            mean_p = sum(values) / len(values)
            m = meta[cid]
            row = MLFeature(
                commune_id=cid,
                reference_date=ref_dt,
                features={
                    "source": "siata",
                    "station_count": len(values),
                    "station_codes": m["station_codes"][:50],
                    "barrios": sorted(m["barrios"])[:30],
                    "mean_precip_mm_snapshot": round(mean_p, 3),
                    "siata_json_url": PLUVIO_JSON,
                },
                precip_acum_7d=None,
                n_events_window=None,
            )
            session.add(row)
            inserted += 1
        await session.commit()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        detail = (detail + " | " if detail else "") + repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source="siata",
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
        )
    return inserted


async def run_siata_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_siata(s)
    return await _run_siata(session)


async def main():
    n = await run_siata_scraper()
    print("siata_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
