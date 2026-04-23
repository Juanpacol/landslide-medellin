from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from scraper.commune import official_to_ml_commune, ring_centroid_lonlat
from scraper.common import httpx_client, log_scrape_run, ml_feature_exists, utcnow, with_retries

GEOMEDELLIN_HUB = "https://geomedellin-m-medellin.opendata.arcgis.com/"
COMUNA_BASE = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11"
)
VM05_BASE = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ordenamiento_ter/VM_05_Amenazas_Movimientos_Masa/MapServer"
)
VM24_BASE = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ordenamiento_ter/VM_24_Densidad_Habitacional_Max/MapServer"
)

COMUNA_CODES = [
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "50",
    "60",
    "70",
    "80",
    "90",
]

DENSITY_LAYERS: list[tuple[int, str]] = [
    (5, "Alta"),
    (4, "Media-alta"),
    (3, "Media-baja"),
    (2, "Baja"),
]


async def _fetch_polygon(client, codigo: str) -> dict[str, Any] | None:
    url = f"{COMUNA_BASE}/query"
    params = {
        "where": f"codigo='{codigo}'",
        "outFields": "codigo,nombre,subtipo_comunacorregimiento",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }

    async def _call():
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    data = await with_retries(_call)
    feats = data.get("features") or []
    if not feats:
        return None
    return feats[0]


async def _query_point_layer(client, base: str, layer_id: int, lon: float, lat: float) -> list[dict[str, Any]]:
    url = f"{base}/{layer_id}/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }

    async def _call():
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    data = await with_retries(_call)
    return data.get("features") or []


async def _collect_medellin_features() -> tuple[list[dict[str, Any]], int, str | None]:
    detail_parts: list[str] = []
    rows: list[dict[str, Any]] = []
    async with httpx_client() as client:
        try:
            r = await client.get(GEOMEDELLIN_HUB)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            anchors = [a.get("href") for a in soup.find_all("a") if a.get("href")]
            detail_parts.append(f"geomedellin_hub_links={len(anchors)}")
        except Exception as exc:  # noqa: BLE001
            detail_parts.append(f"geomedellin_html={repr(exc)}")

        for codigo in COMUNA_CODES:
            feat = await _fetch_polygon(client, codigo)
            if not feat:
                continue
            geom = feat.get("geometry") or {}
            rings = geom.get("rings")
            if not rings:
                continue
            lon, lat = ring_centroid_lonlat(rings)
            attrs = feat.get("attributes") or {}
            subtipo = attrs.get("subtipo_comunacorregimiento")
            ml_id = official_to_ml_commune(str(attrs.get("codigo") or codigo), subtipo)
            if not ml_id:
                continue

            haz_feats = await _query_point_layer(client, VM05_BASE, 2, lon, lat)
            hazard = None
            if haz_feats:
                hazard = (haz_feats[0].get("attributes") or {}).get("grado_amenaza")

            density_band = None
            density_attrs: dict[str, Any] | None = None
            for lid, label in DENSITY_LAYERS:
                dfeats = await _query_point_layer(client, VM24_BASE, lid, lon, lat)
                if dfeats:
                    density_band = label
                    density_attrs = dfeats[0].get("attributes") or {}
                    break

            rows.append(
                {
                    "ml_id": ml_id,
                    "codigo": codigo,
                    "nombre": attrs.get("nombre"),
                    "lon": lon,
                    "lat": lat,
                    "hazard": hazard,
                    "density_band": density_band,
                    "density_attrs": density_attrs or {},
                }
            )

    detail = " | ".join(detail_parts) if detail_parts else None
    return rows, len(rows), detail


async def _run_medellin_datos(session: AsyncSession) -> int:
    started = utcnow()
    status = "error"
    downloaded = 0
    discarded = 0
    inserted = 0
    detail: str | None = None
    ref_dt = utcnow().astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rows, downloaded, detail = await _collect_medellin_features()
        for row in rows:
            ml_id = row["ml_id"]
            exists = await ml_feature_exists(
                session,
                commune_id=ml_id,
                reference_date=ref_dt,
                source_key="medellin_datos",
            )
            if exists:
                discarded += 1
                continue
            da = row["density_attrs"]
            features = {
                "source": "medellin_datos",
                "official_codigo": row["codigo"],
                "nombre": row["nombre"],
                "centroid_lon": round(row["lon"], 6),
                "centroid_lat": round(row["lat"], 6),
                "geomorf_riesgo_grado_amenaza": row["hazard"],
                "densidad_franja": row["density_band"],
                "densidadmax": da.get("densidadmax"),
                "tratamiento": da.get("tratamiento"),
                "geomedellin_hub": GEOMEDELLIN_HUB,
            }
            session.add(
                MLFeature(
                    commune_id=ml_id,
                    reference_date=ref_dt,
                    features=features,
                    precip_acum_7d=None,
                    n_events_window=None,
                )
            )
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
            source="medellin_datos",
            status=status,
            run_started_at=started,
            records_downloaded=downloaded,
            records_valid=inserted,
            records_discarded=discarded,
            detail=detail,
        )
    return inserted


async def run_medellin_datos_scraper(session: AsyncSession | None = None) -> int:
    if session is None:
        async with AsyncSessionLocal() as s:
            return await _run_medellin_datos(s)
    return await _run_medellin_datos(session)


async def main():
    n = await run_medellin_datos_scraper()
    print("medellin_datos_inserted", n)


if __name__ == "__main__":
    asyncio.run(main())
