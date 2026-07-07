from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from db.models.ml_feature import MLFeature
from db.models.rainfall_timeseries import RainfallTimeseries
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

        # Índice de precipitación antecedente por comuna (lluvia ponderada por
        # recencia sobre rainfall_timeseries) — feature ML clave para el modelo.
        from ml.precip_index import FEATURE_KEY as API_KEY, antecedent_indexes_for_all_communes

        try:
            api_by_commune = await antecedent_indexes_for_all_communes(session)
        except Exception as api_exc:  # noqa: BLE001
            logger.warning("No se pudo calcular el índice antecedente: %s", api_exc)
            api_by_commune = {}

        # Intensidad sísmica reciente POR COMUNA (atenuación por distancia real
        # comuna↔epicentro; clave "_default" = valle para comunas sin centroide).
        from ml.seismic_features import FEATURE_KEY as SEISMIC_KEY, seismic_intensity_by_commune

        try:
            seismic_by_commune = await seismic_intensity_by_commune(session)
        except Exception as seis_exc:  # noqa: BLE001
            logger.warning("No se pudo calcular la intensidad sísmica: %s", seis_exc)
            seismic_by_commune = {}

        # % de barrios en amenaza "Alta" por comuna — puente estadístico entre
        # la granularidad de barrio (VM05) y el modelo, que predice por comuna.
        from ml.barrio_hazard_features import FEATURE_KEY as HAZARD_PCT_KEY, pct_barrios_alta_amenaza

        try:
            hazard_pct_by_commune = await pct_barrios_alta_amenaza(session)
        except Exception as hazard_exc:  # noqa: BLE001
            logger.warning("No se pudo calcular pct_barrios_alta_amenaza: %s", hazard_exc)
            hazard_pct_by_commune = {}

        # Soil Water Index (saturación estimada del suelo, metodología JMA).
        from ml.soil_water_index import FEATURE_KEY as SWI_KEY, swi_for_all_communes

        try:
            swi_by_commune = await swi_for_all_communes(session)
        except Exception as swi_exc:  # noqa: BLE001
            logger.warning("No se pudo calcular el Soil Water Index: %s", swi_exc)
            swi_by_commune = {}

        for cid, values in by_commune.items():
            exists = await ml_feature_exists(
                session, commune_id=cid, reference_date=ref_dt, source_key="siata"
            )
            if exists:
                discarded += 1
                continue
            mean_p = sum(values) / len(values)
            m = meta[cid]
            seismic_val = seismic_by_commune.get(cid, seismic_by_commune.get("_default"))
            swi_val = swi_by_commune.get(cid)
            # Interacción sismo × saturación: un sismo sobre suelo saturado es
            # el escenario de mayor riesgo real; como columnas separadas el
            # modelo (árboles poco profundos) difícilmente aprende ese cruce.
            seismic_x_swi = (
                round(seismic_val * (swi_val / 100.0), 4)
                if seismic_val is not None and swi_val is not None
                else None
            )
            row = MLFeature(
                commune_id=cid,
                reference_date=ref_dt,
                features={
                    "source": "siata",
                    "station_count": len(values),
                    "station_codes": m["station_codes"][:50],
                    "barrios": sorted(m["barrios"])[:30],
                    "mean_precip_mm_snapshot": round(mean_p, 3),
                    **({API_KEY: api_by_commune[cid]} if cid in api_by_commune else {}),
                    **({SEISMIC_KEY: seismic_val} if seismic_val is not None else {}),
                    **({HAZARD_PCT_KEY: hazard_pct_by_commune[cid]} if cid in hazard_pct_by_commune else {}),
                    **({SWI_KEY: swi_val} if swi_val is not None else {}),
                    **({"seismic_x_swi": seismic_x_swi} if seismic_x_swi is not None else {}),
                    "siata_json_url": PLUVIO_JSON,
                },
                precip_acum_7d=None,
                n_events_window=None,
            )
            session.add(row)

            # Write to rainfall_timeseries for the live rain monitor (idempotent)
            stmt = (
                pg_insert(RainfallTimeseries)
                .values(
                    commune_id=cid,
                    snapshot_at=ref_dt,
                    precip_mm=round(mean_p, 3),
                    station_count=len(values),
                )
                .on_conflict_do_nothing(index_elements=["commune_id", "snapshot_at"])
            )
            await session.execute(stmt)

            inserted += 1
        await session.commit()
        status = "ok"

        # Check rainfall thresholds and fire Slack alerts if any commune exceeded
        try:
            from alerts.slack import check_and_fire_alerts
            await check_and_fire_alerts(session)
        except Exception as alert_exc:  # noqa: BLE001
            logger.warning("Alert check failed (non-critical): %s", alert_exc)

        # Snake Line: SWI × lluvia intensa cruzando la línea crítica (JMA).
        try:
            from alerts.snake_line import check_and_fire_snake_line_alerts
            await check_and_fire_snake_line_alerts(session, list(by_commune.keys()))
        except Exception as snake_exc:  # noqa: BLE001
            logger.warning("Snake Line alert check failed (non-critical): %s", snake_exc)
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
