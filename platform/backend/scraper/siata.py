from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.rainfall_timeseries import RainfallTimeseries
from db.session import AsyncSessionLocal
from domain.communes import centroid as commune_centroid
from domain.geo import idw_precip
from domain.validation import validate_sensor_reading
from infrastructure.external.arcgis_client import (
    lookup_commune_for_point,
    parse_ml_commune_from_siata_field,
)
from scraper.common import httpx_client, log_scrape_run, ml_feature_exists, utcnow, with_retries

logger = logging.getLogger(__name__)

SIATA_HOME = "https://www.siata.gov.co"
PLUVIO_JSON = "https://siata.gov.co/data/siata_app/Pluviometrica.json"

# Source identifier. Used in `scraping_logs.source`, in `ml_features`'s
# JSONB `source` key, and — since migration b1c2d3e4f501 — in the
# `rainfall_timeseries.source` column, which is part of the unique index.
# One single constant because it used to be repeated in four places: if
# they diverge, `ON CONFLICT` stops matching the index and the whole
# ingestion breaks.
SOURCE_KEY = "siata"


def _floor_minute_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(second=0, microsecond=0)


async def _fetch_siata_home_html(client: httpx.AsyncClient) -> str | None:
    async def _call() -> str | None:
        r = await client.get(SIATA_HOME)
        if r.status_code == 403:
            return None
        r.raise_for_status()
        return r.text

    try:
        return await with_retries(_call)
    except Exception:
        return None


async def _fetch_pluvio(client: httpx.AsyncClient) -> dict[str, Any]:
    async def _call() -> dict[str, Any]:
        r = await client.get(PLUVIO_JSON)
        r.raise_for_status()
        return r.json()

    return await with_retries(_call)


async def _collect_siata_payload() -> tuple[
    dict[str, list[tuple[float, float, float]]],
    dict[str, dict[str, Any]],
    datetime,
    str | None,
    int,
]:
    """Fetch SIATA rain gauge readings and group (lat, lon, value) per commune.

    Station coordinates are kept alongside each value (not discarded after commune
    resolution) so `_run_siata` can aggregate with `domain.geo.idw_precip` instead of a flat
    mean — the mean over all of a commune's stations, including inactive ones reporting ~0,
    is the aggregation bug that zeroed out the rain trigger (audit finding 2,
    docs/research/audit-2026-07.md §4).
    """
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

        by_commune: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
        meta: dict[str, dict[str, Any]] = {}
        cache: dict[tuple[int, int], str | None] = {}

        for st in stations:
            try:
                val = float(st.get("valor"))
            except (TypeError, ValueError):
                continue
            val = validate_sensor_reading(val, field="precip_mm")
            if val is None:
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
            by_commune[ml_id].append((lat, lon, val))
            if ml_id not in meta:
                meta[ml_id] = {"station_codes": [], "barrios": set()}
            meta[ml_id]["station_codes"].append(st.get("codigo"))
            if st.get("barrio"):
                meta[ml_id]["barrios"].add(str(st.get("barrio")))

    return by_commune, meta, ref_dt, detail, raw_count


async def _run_siata(session: AsyncSession) -> int:
    """Ingest SIATA rain readings, derive ML features, and fire post-ingest alerts."""
    started = utcnow()
    status = "error"
    downloaded = 0
    discarded = 0
    inserted = 0
    detail: str | None = None
    try:
        by_commune, meta, ref_dt, detail, downloaded = await _collect_siata_payload()

        # Antecedent precipitation index per commune (rain weighted by
        # recency over rainfall_timeseries) — key ML feature for the model.
        from ml.precip_index import FEATURE_KEY as API_KEY, antecedent_indexes_for_all_communes

        try:
            api_by_commune = await antecedent_indexes_for_all_communes(session)
        except Exception as api_exc:  # noqa: BLE001
            logger.warning("Could not compute the antecedent index: %s", api_exc)
            api_by_commune = {}

        # Recent seismic intensity PER COMMUNE (real commune↔epicenter
        # distance attenuation; "_default" key = valley for communes with no centroid).
        from ml.seismic_features import FEATURE_KEY as SEISMIC_KEY, seismic_intensity_by_commune

        try:
            seismic_by_commune = await seismic_intensity_by_commune(session)
        except Exception as seis_exc:  # noqa: BLE001
            logger.warning("Could not compute seismic intensity: %s", seis_exc)
            seismic_by_commune = {}

        # % of barrios in "Alta" hazard per commune — statistical bridge
        # between barrio granularity (VM05) and the model, which predicts per commune.
        from ml.barrio_hazard_features import (
            FEATURE_KEY as HAZARD_PCT_KEY,
            pct_barrios_alta_amenaza,
        )

        try:
            hazard_pct_by_commune = await pct_barrios_alta_amenaza(session)
        except Exception as hazard_exc:  # noqa: BLE001
            logger.warning("Could not compute pct_barrios_alta_amenaza: %s", hazard_exc)
            hazard_pct_by_commune = {}

        # Soil Water Index (estimated soil saturation, JMA methodology).
        from ml.soil_water_index import FEATURE_KEY as SWI_KEY, swi_for_all_communes

        try:
            swi_by_commune = await swi_for_all_communes(session)
        except Exception as swi_exc:  # noqa: BLE001
            logger.warning("Could not compute the Soil Water Index: %s", swi_exc)
            swi_by_commune = {}

        insufficient_signal = 0
        inserted_communes: list[str] = []
        for cid, points in by_commune.items():
            exists = await ml_feature_exists(
                session, commune_id=cid, reference_date=ref_dt, source_key=SOURCE_KEY
            )
            if exists:
                discarded += 1
                continue

            centroid = commune_centroid(cid)
            mean_p = (
                idw_precip(points, centroid_lat=centroid[0], centroid_lon=centroid[1])
                if centroid is not None
                else None
            )
            if mean_p is None:
                # Fewer than 2 active stations (>0.1mm) reporting for this commune this cycle —
                # writing a 0.0 here is indistinguishable from "confirmed no rain" and is exactly
                # the ambiguity R-QUAL-01/R-QUAL-02 exist to catch. Skip the snapshot instead of
                # fabricating a number (audit finding 2).
                insufficient_signal += 1
                discarded += 1
                continue

            values = [v for _, _, v in points]
            m = meta[cid]
            seismic_val = seismic_by_commune.get(cid, seismic_by_commune.get("_default"))
            swi_val = swi_by_commune.get(cid)
            # Seismic × saturation interaction: a quake on saturated soil is
            # the highest real-risk scenario; as separate columns the model
            # (shallow trees) is unlikely to learn that cross-term.
            seismic_x_swi = (
                round(seismic_val * (swi_val / 100.0), 4)
                if seismic_val is not None and swi_val is not None
                else None
            )
            row = MLFeature(
                commune_id=cid,
                reference_date=ref_dt,
                features={
                    "source": SOURCE_KEY,
                    "station_count": len(values),
                    "station_codes": m["station_codes"][:50],
                    "barrios": sorted(m["barrios"])[:30],
                    "mean_precip_mm_snapshot": round(mean_p, 3),
                    **({API_KEY: api_by_commune[cid]} if cid in api_by_commune else {}),
                    **({SEISMIC_KEY: seismic_val} if seismic_val is not None else {}),
                    **(
                        {HAZARD_PCT_KEY: hazard_pct_by_commune[cid]}
                        if cid in hazard_pct_by_commune
                        else {}
                    ),
                    **({SWI_KEY: swi_val} if swi_val is not None else {}),
                    **({"seismic_x_swi": seismic_x_swi} if seismic_x_swi is not None else {}),
                    "siata_json_url": PLUVIO_JSON,
                },
                precip_acum_7d=None,
                n_events_window=None,
            )
            session.add(row)

            # Write to rainfall_timeseries for the live rain monitor (idempotent).
            # `source` is MANDATORY in the conflict clause: the unique index
            # has been (commune_id, snapshot_at, source) since migration
            # b1c2d3e4f501. Without the third column, Postgres finds no
            # matching index and aborts with InvalidColumnReferenceError,
            # taking down the whole ingestion.
            stmt = (
                pg_insert(RainfallTimeseries)
                .values(
                    commune_id=cid,
                    snapshot_at=ref_dt,
                    precip_mm=round(mean_p, 3),
                    station_count=len(values),
                    source=SOURCE_KEY,
                )
                .on_conflict_do_nothing(index_elements=["commune_id", "snapshot_at", "source"])
            )
            await session.execute(stmt)

            inserted += 1
            inserted_communes.append(cid)
        await session.commit()
        status = "ok"
        if insufficient_signal:
            detail = (detail + " | " if detail else "") + (
                f"insufficient_signal={insufficient_signal} communes (<2 active stations)"
            )

        # Post-ingestion alert checks (daily threshold + Snake Line) — the
        # composition lives in application/fire_alerts.py; never takes down the run.
        from application.fire_alerts import alerts_after_rain_ingest

        await alerts_after_rain_ingest(session, inserted_communes)
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
        )
    return inserted


async def run_siata_scraper(session: AsyncSession | None = None) -> int:
    """Run the SIATA rain scraper, opening a session if one isn't provided."""
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_siata(s)
    return await _run_siata(session)


async def main() -> None:
    """Run the SIATA scraper and print the number of inserted features."""
    n = await run_siata_scraper()
    print("siata_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
