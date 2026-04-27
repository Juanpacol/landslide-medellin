from __future__ import annotations

import asyncio
import argparse
import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.landslide_event import LandslideEvent
from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from scraper.commune import lookup_commune_for_point
from scraper.common import httpx_client, ml_feature_exists, with_retries

WP_POSTS_URL = "https://www.medellin.gov.co/es/wp-json/wp/v2/posts"
IDEAM_S54A_URL = "https://www.datos.gov.co/resource/s54a-sgyg.json"
SIATA_PLUVIO_META = "https://siata.gov.co/data/siata_app/Pluviometrica.json"
SIATA_HIST_BASE = "https://siata.gov.co/hidrologia/temperatura_agualluvia"
MEDATA_DATA_JSON = "https://medata.gov.co/data.json"
MEDATA_ALERTS_CSV = (
    "https://medata.gov.co/sites/default/files/distribution/1-020-13-000423/"
    "alertas_asociadas_factores_riesgos_identificados_satmed.csv"
)

SIATA_FILES = ["7.txt", "20.txt", "41.txt", "54.txt", "56.txt", "311.txt", "198.txt", "362.txt"]
MIN_YEAR = 2018

LANDSLIDE_KEYWORDS = (
    "desliz",
    "movimiento en masa",
    "movimientos en masa",
    "derrumbe",
    "emergencia",
    "avenida torrencial",
)

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


async def _landslide_exists(session: AsyncSession, source_row_id: str) -> bool:
    stmt = select(LandslideEvent.id).where(LandslideEvent.source_row_id == source_row_id).limit(1)
    return bool(await session.scalar(stmt))


async def ingest_historical_dagrd(session: AsyncSession) -> dict[str, Any]:
    years = Counter()
    inserted = 0
    fetched = 0
    seen_ids: set[int] = set()
    async with httpx_client() as client:
        page = 1
        while True:
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
                pid = int(p.get("id", 0))
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                title = ((p.get("title") or {}).get("rendered") or "").strip()
                content = ((p.get("content") or {}).get("rendered") or "").strip()
                blob = f"{title} {content}".lower()
                if not any(k in blob for k in LANDSLIDE_KEYWORDS):
                    continue
                dt = _parse_dt(p.get("date") or p.get("date_gmt") or "")
                if not dt or dt.year < MIN_YEAR:
                    continue
                years[str(dt.year)] += 1
                sid = f"historical_dagrd:wp:{pid}"
                if await _landslide_exists(session, sid):
                    continue
                commune = _commune_from_text(blob)
                session.add(
                    LandslideEvent(
                        source_row_id=sid,
                        fecha=dt.date().isoformat(),
                        tipo_emergencia=(title or "Evento DAGRD histórico")[:500],
                        commune_id=commune,
                        barrio=None,
                        latitud=None,
                        longitud=None,
                        has_coords=False,
                    )
                )
                inserted += 1
            page += 1
            if page > 30:
                break
    await session.commit()
    result = {"source": "historical_dagrd", "fetched": fetched, "inserted": inserted, "by_year": dict(years)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def ingest_historical_ideam(session: AsyncSession) -> dict[str, Any]:
    cache_commune: dict[tuple[float, float], str | None] = {}
    by_commune_day: dict[tuple[str, datetime], list[float]] = defaultdict(list)
    years = Counter()
    fetched = 0
    inserted = 0

    async with httpx_client(timeout=120.0) as client:
        offset = 0
        limit = 5000
        while True:
            where = "upper(municipio) like '%MEDELL%' and fechaobservacion >= '2018-01-01T00:00:00.000'"
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
            print(f"historical_ideam page offset={offset} rows={len(batch)} fetched={fetched}", flush=True)
            for row in batch:
                dt = _parse_dt(row.get("fechaobservacion", ""))
                if not dt or dt.year < MIN_YEAR:
                    continue
                years[str(dt.year)] += 1
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
                day = _to_utc_day(dt)
                by_commune_day[(cid, day)].append(val)
            if len(batch) < limit:
                break
            offset += limit
            if offset > 240_000:
                break

    for (cid, day), vals in by_commune_day.items():
        if await ml_feature_exists(
            session, commune_id=cid, reference_date=day, source_key="historical_ideam"
        ):
            continue
        session.add(
            MLFeature(
                commune_id=cid,
                reference_date=day,
                features={
                    "source": "historical_ideam",
                    "dataset": "s54a-sgyg",
                    "precip_records": len(vals),
                    "precip_sum_mm_day": round(sum(vals), 3),
                },
                precip_acum_7d=None,
                n_events_window=None,
            )
        )
        inserted += 1
    await session.commit()
    result = {"source": "historical_ideam", "fetched": fetched, "inserted": inserted, "by_year": dict(years)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def ingest_historical_siata(session: AsyncSession) -> dict[str, Any]:
    years = Counter()
    fetched = 0
    inserted = 0

    async with httpx_client(timeout=180.0) as client:
        meta = await with_retries(lambda: client.get(SIATA_PLUVIO_META))
        meta.raise_for_status()
        stations = (meta.json() or {}).get("estaciones") or []
        station_to_latlon: dict[str, tuple[float, float]] = {}
        for st in stations:
            code = str(st.get("codigo"))
            try:
                station_to_latlon[code] = (float(st.get("latitud")), float(st.get("longitud")))
            except (TypeError, ValueError):
                continue

        by_commune_day: dict[tuple[str, datetime], list[float]] = defaultdict(list)
        commune_cache: dict[str, str | None] = {}

        for fname in SIATA_FILES:
            url = f"{SIATA_HIST_BASE}/{fname}"

            async def _dl():
                r = await client.get(url)
                r.raise_for_status()
                return r.text

            text = await with_retries(_dl)
            if not text.strip():
                continue
            print(f"historical_siata file={fname} bytes={len(text)}", flush=True)
            df = pd.read_csv(
                io.StringIO(text),
                sep="\t",
                header=None,
                usecols=[0, 1, 2],
                names=["station", "fecha", "precip"],
                dtype={"station": "string", "fecha": "string", "precip": "float64"},
                on_bad_lines="skip",
            )
            if df.empty:
                continue
            df["dt"] = pd.to_datetime(df["fecha"], errors="coerce", utc=True)
            df = df.dropna(subset=["dt", "precip"])
            df = df[df["dt"].dt.year >= MIN_YEAR]
            if df.empty:
                continue
            fetched += len(df)
            yr_counts = df["dt"].dt.year.value_counts()
            for y, c in yr_counts.items():
                years[str(int(y))] += int(c)

            for st_code in sorted(df["station"].dropna().unique().tolist()):
                if st_code in commune_cache:
                    continue
                latlon = station_to_latlon.get(str(st_code))
                if not latlon:
                    commune_cache[st_code] = None
                else:
                    info = await lookup_commune_for_point(client, latlon[1], latlon[0])
                    commune_cache[st_code] = info.get("ml_commune_id")

            df["cid"] = df["station"].map(lambda x: commune_cache.get(str(x)))
            df = df[df["cid"].notna()]
            if df.empty:
                continue
            df["day"] = df["dt"].dt.floor("D")
            grouped = df.groupby(["cid", "day"], as_index=False)["precip"].sum()
            for _, row in grouped.iterrows():
                day = row["day"].to_pydatetime().astimezone(timezone.utc)
                by_commune_day[(str(row["cid"]), _to_utc_day(day))].append(float(row["precip"]))

    pending = list(by_commune_day.items())
    chunk_size = 400
    for i in range(0, len(pending), chunk_size):
        async with AsyncSessionLocal() as write_session:
            chunk = pending[i : i + chunk_size]
            for (cid, day), vals in chunk:
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
                            "siata_files": SIATA_FILES,
                            "precip_records": len(vals),
                            "precip_sum_mm_day": round(sum(vals), 3),
                        },
                        precip_acum_7d=None,
                        n_events_window=None,
                    )
                )
                inserted += 1
            await write_session.commit()
    result = {"source": "historical_siata", "fetched": fetched, "inserted": inserted, "by_year": dict(years)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def ingest_historical_medata(session: AsyncSession) -> dict[str, Any]:
    years = Counter()
    fetched = 0
    inserted = 0

    def _load_json(url: str) -> dict[str, Any]:
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        return r.json()

    def _load_text(url: str) -> str:
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        return r.text

    csv_text = await asyncio.to_thread(_load_text, MEDATA_ALERTS_CSV)
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    chunk_size = 500
    for i in range(0, len(rows), chunk_size):
        async with AsyncSessionLocal() as write_session:
            chunk = rows[i : i + chunk_size]
            for row in chunk:
                dt = _parse_dt((row.get("createdAt") or "").replace("-05:00", "+00:00"))
                if not dt or dt.year < MIN_YEAR:
                    continue
                fetched += 1
                years[str(dt.year)] += 1
                sid = f"historical_medata:salvavidas:{row.get('id')}"
                if await _landslide_exists(write_session, sid):
                    continue
                write_session.add(
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
            await write_session.commit()
    result = {"source": "historical_medata", "fetched": fetched, "inserted": inserted, "by_year": dict(years)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


async def table_totals(session: AsyncSession) -> dict[str, int]:
    ml_total = await session.scalar(select(func.count()).select_from(MLFeature))
    le_total = await session.scalar(select(func.count()).select_from(LandslideEvent))
    return {"ml_features": int(ml_total or 0), "landslide_events": int(le_total or 0)}


async def main(run_only: str | None) -> None:
    async with AsyncSessionLocal() as session:
        out = []
        if run_only in (None, "dagrd"):
            out.append(await ingest_historical_dagrd(session))
        if run_only in (None, "ideam"):
            out.append(await ingest_historical_ideam(session))
        if run_only in (None, "siata"):
            out.append(await ingest_historical_siata(session))
        if run_only in (None, "medata"):
            out.append(await ingest_historical_medata(session))
        totals = await table_totals(session)
    print(json.dumps({"sources": out, "table_totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["dagrd", "ideam", "siata", "medata"], default=None)
    args = parser.parse_args()
    asyncio.run(main(args.only))
