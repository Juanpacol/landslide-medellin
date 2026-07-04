from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.landslide_event import LandslideEvent
from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from scraper.commune import lookup_commune_for_point
from scraper.common import httpx_client, log_scrape_run, ml_feature_exists, utcnow, with_retries

WP_POSTS_URL = "https://www.medellin.gov.co/es/wp-json/wp/v2/posts"
IDEAM_S54A_URL = "https://www.datos.gov.co/resource/s54a-sgyg.json"
SIATA_PLUVIO_META = "https://siata.gov.co/data/siata_app/Pluviometrica.json"
SIATA_HIST_BASE = "https://siata.gov.co/hidrologia/temperatura_agualluvia"
MEDATA_ALERTS_CSV = (
    "https://medata.gov.co/sites/default/files/distribution/1-020-13-000423/"
    "alertas_asociadas_factores_riesgos_identificados_satmed.csv"
)

SIATA_FILES = ["7.txt", "20.txt", "41.txt", "54.txt", "56.txt", "311.txt", "198.txt", "362.txt"]
LANDSLIDE_KEYWORDS = ("desliz", "movimiento en masa", "derrumbe", "emergencia", "avenida torrencial")
_CORREG_TO_ML = {"50": "17", "60": "18", "70": "19", "80": "20", "90": "21"}


def _to_utc_day(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _commune_from_text(text: str) -> str | None:
    m = re.search(r"comuna\s*(\d{1,2})\b", text, flags=re.IGNORECASE)
    if m:
        return str(int(m.group(1)))
    m2 = re.search(r"corregimiento\s*(\d{2,3})\b", text, flags=re.IGNORECASE)
    if m2:
        return _CORREG_TO_ML.get(m2.group(1))
    return None


async def _max_ml_date(session: AsyncSession, source: str) -> datetime | None:
    stmt = select(func.max(MLFeature.reference_date)).where(MLFeature.features["source"].as_string() == source)
    return await session.scalar(stmt)


async def _landslide_exists(session: AsyncSession, sid: str) -> bool:
    stmt = select(LandslideEvent.id).where(LandslideEvent.source_row_id == sid).limit(1)
    return bool(await session.scalar(stmt))


async def ingest_ideam_incremental() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        return await _ingest_ideam_incremental_session(session)


async def _ingest_ideam_incremental_session(session: AsyncSession) -> tuple[int, int]:
    last = await _max_ml_date(session, "historical_ideam")
    start = (last - timedelta(days=2)) if last else datetime(2018, 1, 1, tzinfo=timezone.utc)
    fetched = 0
    inserted = 0
    by_commune_day: dict[tuple[str, datetime], list[float]] = defaultdict(list)
    cache_commune: dict[tuple[float, float], str | None] = {}

    async with httpx_client(timeout=120.0) as client:
        offset = 0
        limit = 5000
        while True:
            where = (
                f"upper(municipio) like '%MEDELL%' and "
                f"fechaobservacion >= '{start.strftime('%Y-%m-%dT%H:%M:%S.000')}'"
            )
            params = {
                "$where": where,
                "$select": "fechaobservacion,latitud,longitud,valorobservado",
                "$limit": str(limit),
                "$offset": str(offset),
            }

            async def _call():
                r = await client.get(IDEAM_S54A_URL, params=params)
                r.raise_for_status()
                return r.json()

            batch = await with_retries(_call)
            if not isinstance(batch, list) or not batch:
                break
            fetched += len(batch)
            for row in batch:
                dt = _parse_dt(row.get("fechaobservacion", ""))
                if not dt:
                    continue
                try:
                    lat = float(row.get("latitud"))
                    lon = float(row.get("longitud"))
                    val = float(row.get("valorobservado") or 0)
                except (TypeError, ValueError):
                    continue
                key = (round(lat, 4), round(lon, 4))
                if key not in cache_commune:
                    info = await lookup_commune_for_point(client, lon, lat)
                    cache_commune[key] = info.get("ml_commune_id")
                cid = cache_commune[key]
                if not cid:
                    continue
                by_commune_day[(cid, _to_utc_day(dt))].append(val)
            if len(batch) < limit:
                break
            offset += limit
            if offset > 100_000:
                break

    for (cid, day), vals in by_commune_day.items():
        if await ml_feature_exists(session, commune_id=cid, reference_date=day, source_key="historical_ideam"):
            continue
        session.add(
            MLFeature(
                commune_id=cid,
                reference_date=day,
                features={
                    "source": "historical_ideam",
                    "dataset": "s54a-sgyg",
                    "incremental": True,
                    "precip_records": len(vals),
                    "precip_sum_mm_day": round(sum(vals), 3),
                },
                precip_acum_7d=None,
                n_events_window=None,
            )
        )
        inserted += 1
    await session.commit()
    return fetched, inserted


async def ingest_siata_incremental() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        return await _ingest_siata_incremental_session(session)


async def _ingest_siata_incremental_session(session: AsyncSession) -> tuple[int, int]:
    last = await _max_ml_date(session, "historical_siata")
    start_day = (last - timedelta(days=2)) if last else datetime(2018, 1, 1, tzinfo=timezone.utc)
    fetched = 0
    inserted = 0

    async with httpx_client(timeout=180.0) as client:
        meta_resp = await with_retries(lambda: client.get(SIATA_PLUVIO_META))
        meta_resp.raise_for_status()
        stations = (meta_resp.json() or {}).get("estaciones") or []
        station_to_latlon: dict[str, tuple[float, float]] = {}
        for st in stations:
            try:
                station_to_latlon[str(st.get("codigo"))] = (float(st.get("latitud")), float(st.get("longitud")))
            except (TypeError, ValueError):
                continue

        commune_cache: dict[str, str | None] = {}
        agg: dict[tuple[str, datetime], list[float]] = defaultdict(list)

        for fname in SIATA_FILES:
            url = f"{SIATA_HIST_BASE}/{fname}"

            async def _dl():
                r = await client.get(url)
                r.raise_for_status()
                return r.text

            text = await with_retries(_dl)
            if not text.strip():
                continue
            df = pd.read_csv(
                io.StringIO(text),
                sep="\t",
                header=None,
                usecols=[0, 1, 2],
                names=["station", "fecha", "precip"],
                on_bad_lines="skip",
            )
            if df.empty:
                continue
            df["dt"] = pd.to_datetime(df["fecha"], format="%Y-%m-%d %H:%M:%S", errors="coerce", utc=True)
            df = df.dropna(subset=["dt", "precip"])
            df = df[df["dt"] >= start_day]
            if df.empty:
                continue
            fetched += len(df)
            for st_code in sorted(df["station"].astype(str).unique().tolist()):
                if st_code in commune_cache:
                    continue
                latlon = station_to_latlon.get(st_code)
                if not latlon:
                    commune_cache[st_code] = None
                else:
                    info = await lookup_commune_for_point(client, latlon[1], latlon[0])
                    commune_cache[st_code] = info.get("ml_commune_id")
            df["cid"] = df["station"].astype(str).map(lambda x: commune_cache.get(x))
            df = df[df["cid"].notna()]
            if df.empty:
                continue
            df["day"] = df["dt"].dt.floor("D")
            grouped = df.groupby(["cid", "day"], as_index=False)["precip"].sum()
            for _, r in grouped.iterrows():
                day = r["day"].to_pydatetime().astimezone(timezone.utc)
                agg[(str(r["cid"]), _to_utc_day(day))].append(float(r["precip"]))

    # Re-open short-lived sessions while writing to avoid stale asyncpg connections.
    pending = list(agg.items())
    chunk_size = 300
    for i in range(0, len(pending), chunk_size):
        async with AsyncSessionLocal() as write_session:
            for (cid, day), vals in pending[i : i + chunk_size]:
                if await ml_feature_exists(
                    write_session, commune_id=cid, reference_date=day, source_key="historical_siata"
                ):
                    continue
                write_session.add(
                    MLFeature(
                        commune_id=cid,
                        reference_date=day,
                        features={
                            "source": "historical_siata",
                            "incremental": True,
                            "precip_records": len(vals),
                            "precip_sum_mm_day": round(sum(vals), 3),
                        },
                        precip_acum_7d=None,
                        n_events_window=None,
                    )
                )
                inserted += 1
            await write_session.commit()
    return fetched, inserted


async def ingest_dagrd_incremental() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        return await _ingest_dagrd_incremental_session(session)


async def _ingest_dagrd_incremental_session(session: AsyncSession) -> tuple[int, int]:
    fetched = 0
    inserted = 0
    # Cache existing DAGRD historical IDs to avoid one DB roundtrip per post.
    existing_stmt = select(LandslideEvent.source_row_id).where(
        LandslideEvent.source_row_id.like("historical_dagrd:%")
    )
    existing_rows = await session.execute(existing_stmt)
    existing_ids = {r[0] for r in existing_rows if r[0]}

    async with httpx_client() as client:
        for page in range(1, 6):
            params = {"search": "deslizamiento", "per_page": 100, "page": page}

            async def _call():
                r = await client.get(WP_POSTS_URL, params=params)
                if r.status_code == 400:
                    return []
                r.raise_for_status()
                return r.json()

            posts = await with_retries(_call)
            if not posts:
                break
            fetched += len(posts)
            for p in posts:
                pid = int(p.get("id") or 0)
                if not pid:
                    continue
                title = ((p.get("title") or {}).get("rendered") or "").strip()
                content = ((p.get("content") or {}).get("rendered") or "").strip()
                blob = f"{title} {content}".lower()
                if not any(k in blob for k in LANDSLIDE_KEYWORDS):
                    continue
                dt = _parse_dt(p.get("date") or p.get("date_gmt") or "")
                if not dt:
                    continue
                sid = f"historical_dagrd:wp:{pid}"
                if sid in existing_ids:
                    continue
                session.add(
                    LandslideEvent(
                        source_row_id=sid,
                        fecha=dt.date().isoformat(),
                        tipo_emergencia=(title or "Evento DAGRD histórico")[:500],
                        commune_id=_commune_from_text(blob),
                        barrio=None,
                        latitud=None,
                        longitud=None,
                        has_coords=False,
                    )
                )
                inserted += 1
                existing_ids.add(sid)
    await session.commit()
    return fetched, inserted


async def ingest_medata_incremental() -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        return await _ingest_medata_incremental_session(session)


async def _ingest_medata_incremental_session(session: AsyncSession) -> tuple[int, int]:
    fetched = 0
    inserted = 0

    existing_stmt = select(LandslideEvent.source_row_id).where(
        LandslideEvent.source_row_id.like("historical_medata:%")
    )
    existing_rows = await session.execute(existing_stmt)
    existing_ids = {r[0] for r in existing_rows if r[0]}

    text = await asyncio.to_thread(lambda: requests.get(MEDATA_ALERTS_CSV, timeout=300).text)
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        dt = _parse_dt((row.get("createdAt") or "").replace("-05:00", "+00:00"))
        if not dt:
            continue
        fetched += 1
        sid = f"historical_medata:salvavidas:{row.get('id')}"
        if sid in existing_ids:
            continue
        session.add(
            LandslideEvent(
                source_row_id=sid,
                fecha=dt.date().isoformat(),
                tipo_emergencia=f"Alerta factor_riesgo_id={row.get('FACTOR_RIESGO_ID')}",
                commune_id=None,
                barrio=None,
                latitud=None,
                longitud=None,
                has_coords=False,
            )
        )
        inserted += 1
        existing_ids.add(sid)
    await session.commit()
    return fetched, inserted


async def run_incremental(only: str | None = None) -> dict[str, Any]:
    started = utcnow()
    result: dict[str, Any] = {"started_at": started.isoformat(), "sources": {}}

    runners = (
        ("historical_dagrd_incremental", ingest_dagrd_incremental, "dagrd"),
        ("historical_ideam_incremental", ingest_ideam_incremental, "ideam"),
        ("historical_siata_incremental", ingest_siata_incremental, "siata"),
        ("historical_medata_incremental", ingest_medata_incremental, "medata"),
    )

    for name, fn, slug in runners:
        if only and only != slug:
            continue
        status = "ok"
        detail = "incremental run"
        fetched = 0
        inserted = 0
        try:
            fetched, inserted = await fn()
            result["sources"][name] = {"status": "ok", "fetched": fetched, "inserted": inserted}
        except Exception as exc:  # noqa: BLE001
            status = "error"
            detail = repr(exc)
            result["sources"][name] = {"status": "error", "error": detail}
        async with AsyncSessionLocal() as log_session:
            await log_scrape_run(
                log_session,
                source=name,
                status=status,
                run_started_at=started,
                records_downloaded=fetched,
                records_valid=inserted,
                records_discarded=max(fetched - inserted, 0),
                detail=detail,
            )
    result["finished_at"] = utcnow().isoformat()
    return result


async def main(only: str | None) -> None:
    out = await run_incremental(only=only)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["dagrd", "ideam", "siata", "medata"], default=None)
    args = parser.parse_args()
    asyncio.run(main(args.only))
