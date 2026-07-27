"""
Scraper de sismos SIATA — red de sismógrafos y acelerógrafos del Valle de Aburrá.

Fuente: los GeoJSON del geoportal de ingeniería sísmica de SIATA. Cada archivo
trae las estaciones como Features; cada estación publica hasta 3 eventos
recientes (`evento_1..3`) con magnitud, profundidad, epicentro y coordenadas.
Los archivos pesan 4-10 KB y solo cambian cuando hay un sismo nuevo, así que
el polling de 30 min sobra.

Formato real de un evento (confirmado contra el feed en producción):
    "informacion": {
        "fecha_local": "2026-02-19 19:33:50",
        "magnitud": "1.6",
        "longitud": "-75.67°",
        "latitud": "6.19°",
        "profundidad": "13 km",
        "epicentro": "Sismo en Medellín - Antioquia"
    }
Los números vienen como strings con unidad/símbolo — se parsean tolerantes.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.seismic_event import SeismicEvent
from db.session import AsyncSessionLocal
from scraper.common import httpx_client, log_scrape_run, utcnow, with_retries

logger = logging.getLogger(__name__)

COL_TZ = ZoneInfo("America/Bogota")

FEED_URLS = [
    "https://siata.gov.co/ingenieria_sismica/geoportal/ultimos_sismos/sismografos/ultimos_sismos_sismografos.geojson",
    "https://siata.gov.co/ingenieria_sismica/geoportal/ultimos_sismos/acelerografos/ultimos_sismos_acelerografos.geojson",
]


def _parse_number(raw: Any) -> float | None:
    """'1.6' / '-75.67°' / '172 km' → float. None si no hay número."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(raw))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _parse_local_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=COL_TZ)
    except ValueError:
        return None


def _extract_events(feature: dict[str, Any]) -> list[dict[str, Any]]:
    """Aplana los `evento_N` de una estación en registros individuales."""
    props = feature.get("properties") or {}
    station_code = str(props.get("codigo") or props.get("estacion") or "desconocida")
    station_name = str(props.get("nombre") or station_code)

    rows: list[dict[str, Any]] = []
    for key, value in props.items():
        if not key.startswith("evento_") or not isinstance(value, dict):
            continue
        info = value.get("informacion") or {}
        fecha_local = info.get("fecha_local")
        if not fecha_local:
            continue
        rows.append(
            {
                "source_row_id": f"{station_code}_{fecha_local}",
                "station_code": station_code,
                "station_name": station_name,
                "event_local_at": _parse_local_dt(fecha_local),
                "magnitude": _parse_number(info.get("magnitud")),
                "depth_km": _parse_number(info.get("profundidad")),
                "epicenter_lat": _parse_number(info.get("latitud")),
                "epicenter_lon": _parse_number(info.get("longitud")),
                "epicenter_label": info.get("epicentro"),
            }
        )
    return rows


async def _collect_seismic_rows() -> tuple[list[dict[str, Any]], int, str]:
    rows: list[dict[str, Any]] = []
    detail_parts: list[str] = []
    downloaded = 0
    async with httpx_client() as client:
        for url in FEED_URLS:
            kind = "sismografos" if "sismografos" in url else "acelerografos"

            async def _call(u: str = url) -> dict[str, Any]:
                r = await client.get(u)
                r.raise_for_status()
                return r.json()

            try:
                data = await with_retries(_call)
            except Exception as exc:  # noqa: BLE001
                detail_parts.append(f"{kind}={repr(exc)}")
                continue

            features = data.get("features") or []
            downloaded += len(features)
            for feat in features:
                rows.extend(_extract_events(feat))
            detail_parts.append(f"{kind}={len(features)} estaciones")

    return rows, downloaded, " | ".join(detail_parts)


async def _event_exists(session: AsyncSession, source_row_id: str) -> bool:
    stmt = select(SeismicEvent.id).where(SeismicEvent.source_row_id == source_row_id).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _run_siata_sismos(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    inserted = 0
    discarded = 0
    detail: str | None = None
    new_items: list[dict[str, Any]] = []
    try:
        rows, downloaded, detail = await _collect_seismic_rows()

        for row in rows:
            if await _event_exists(session, row["source_row_id"]):
                discarded += 1
                continue
            session.add(SeismicEvent(**row))
            inserted += 1
            new_items.append(
                {
                    "titulo": row.get("epicenter_label") or "Sismo registrado",
                    "detalle": (
                        f"M{row['magnitude']}"
                        if row.get("magnitude") is not None
                        else "magnitud s/d"
                    )
                    + (
                        f" · {row['depth_km']:.0f} km de profundidad"
                        if row.get("depth_km") is not None
                        else ""
                    )
                    + f" · estación {row['station_name']}",
                    "fecha": str(row.get("event_local_at") or ""),
                }
            )

        await session.commit()
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        detail = (detail + " | " if detail else "") + repr(exc)
        await session.rollback()
        raise
    finally:
        await log_scrape_run(
            session,
            source="siata_sismos",
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
            new_items_summary=new_items if status == "ok" else None,
        )
    return inserted


async def run_siata_sismos_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_siata_sismos(s)
    return await _run_siata_sismos(session)


async def main() -> None:
    n = await run_siata_sismos_scraper()
    print("siata_sismos_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
