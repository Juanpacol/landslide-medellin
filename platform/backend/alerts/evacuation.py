"""
Rutas de evacuación — MVP sin datos propios de zonas seguras.

En vez de pedir que alguien mapee manualmente 40-60 puntos de encuentro (no
verificable por código), se usan dos servicios públicos y gratuitos:

1. Overpass API (OpenStreetMap) — candidatos a zona segura: parques, colegios
   y estadios existentes dentro de Medellín. Sin API key.
2. OSRM demo server (router.project-osrm.org) — ruta caminando desde el
   origen hasta la zona segura más cercana. Sin API key, servidor público de
   demostración (no apto para alto volumen, suficiente para este MVP).

IMPORTANTE — sin validar: ninguna de estas zonas ha sido confirmada por
Defensoría Civil o DAGRD como punto de encuentro oficial de emergencia. Toda
respuesta de este módulo debe tratarse como una sugerencia geográfica
razonable, no como un protocolo de evacuación oficial. Se marca
`"validated": false` explícitamente en cada resultado.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.safe_zone import SafeZone
from scraper.commune import haversine_km
from scraper.common import httpx_client, with_retries

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/foot"

# Bounding box de Medellín (mismo usado para el grid de Mesh Maps).
MEDELLIN_BBOX = (5.95, -75.75, 6.35, -75.45)  # (south, west, north, east)

_OVERPASS_QUERY = (
    "[out:json][timeout:25];"
    '(node["leisure"="park"]({south},{west},{north},{east});'
    'way["leisure"="park"]({south},{west},{north},{east});'
    'node["amenity"="school"]({south},{west},{north},{east});'
    'way["amenity"="school"]({south},{west},{north},{east});'
    'node["leisure"="stadium"]({south},{west},{north},{east});'
    'way["leisure"="stadium"]({south},{west},{north},{east});'
    ");out center;"
)

_TYPE_BY_TAG = {"park": "park", "school": "school", "stadium": "stadium"}


async def fetch_safe_zones_osm(bbox: tuple[float, float, float, float] = MEDELLIN_BBOX) -> list[dict[str, Any]]:
    """Consulta Overpass API por parques/colegios/estadios dentro del bbox."""
    south, west, north, east = bbox
    query = _OVERPASS_QUERY.format(south=south, west=west, north=north, east=east)

    # Overpass rechaza (406) el POST con el Accept/User-Agent de navegador que
    # usa httpx_client por defecto para los demás scrapers, y también el GET
    # si httpx codifica los espacios como "+" en vez de "%20" (esta instancia
    # de Overpass devuelve 406 genérico de Apache con "+" literal). Se
    # construye la query string codificada a mano para evitarlo.
    import urllib.parse

    headers = {"User-Agent": "TEYVA-Scraper/1.0 (contacto: jbotero@aztia.co)", "Accept": "*/*"}
    encoded_query = urllib.parse.quote(query, safe="")
    url = f"{OVERPASS_URL}?data={encoded_query}"
    async with httpx_client(timeout=30.0, headers=headers) as client:
        response = await with_retries(lambda: client.get(url))
        response.raise_for_status()
        data = response.json()

    zones: list[dict[str, Any]] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        nombre = tags.get("name")
        if not nombre:
            continue
        tipo = None
        if tags.get("leisure") == "park":
            tipo = "park"
        elif tags.get("amenity") == "school":
            tipo = "school"
        elif tags.get("leisure") == "stadium":
            tipo = "stadium"
        if tipo is None:
            continue

        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue

        zones.append({
            "id": f"osm_{el.get('type')}_{el.get('id')}",
            "nombre": nombre,
            "tipo": tipo,
            "lat": float(lat),
            "lon": float(lon),
        })
    return zones


async def refresh_safe_zones(session: AsyncSession) -> int:
    """Descarga candidatos de Overpass y los upserta en `safe_zones`."""
    zones = await fetch_safe_zones_osm()
    for z in zones:
        stmt = (
            pg_insert(SafeZone)
            .values(**z, validated=False)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={"nombre": z["nombre"], "tipo": z["tipo"], "lat": z["lat"], "lon": z["lon"]},
            )
        )
        await session.execute(stmt)
    await session.commit()
    return len(zones)


async def _commune_centroid(session: AsyncSession, commune_id: str) -> tuple[float, float] | None:
    """Centroide de la comuna, reusando `centroid_lat`/`centroid_lon` que ya
    escribe `scraper/medellin_datos.py` en MLFeature.features — no se inventan
    coordenadas nuevas."""
    stmt = (
        select(MLFeature.features)
        .where(MLFeature.commune_id == commune_id, MLFeature.features.isnot(None))
        .order_by(MLFeature.reference_date.desc().nulls_last())
    )
    for (features,) in (await session.execute(stmt)).all():
        if not isinstance(features, dict):
            continue
        lat, lon = features.get("centroid_lat"), features.get("centroid_lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    return None


async def _osrm_walking_route(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> dict[str, Any] | None:
    from infrastructure.external.osrm_client import walking_route

    return await walking_route(origin_lat, origin_lon, dest_lat, dest_lon)


async def get_evacuation_routes(
    session: AsyncSession, commune_id: str, *, top_n: int = 3
) -> dict[str, Any]:
    """Zonas seguras candidatas más cercanas a una comuna, con ruta caminando
    a la más cercana. Ver disclaimer del módulo — MVP sin validar."""
    origin = await _commune_centroid(session, commune_id)
    if origin is None:
        return {
            "commune_id": commune_id,
            "validated": False,
            "error": "Sin centroide conocido para esta comuna todavía.",
            "zones": [],
        }
    origin_lat, origin_lon = origin

    zones = (await session.execute(select(SafeZone))).scalars().all()
    if not zones:
        return {
            "commune_id": commune_id,
            "validated": False,
            "error": "Sin zonas seguras cargadas — correr alerts.evacuation.refresh_safe_zones primero.",
            "zones": [],
        }

    ranked = sorted(
        zones,
        key=lambda z: haversine_km(origin_lon, origin_lat, z.lon, z.lat),
    )[:top_n]

    results = []
    for z in ranked:
        straight_km = round(haversine_km(origin_lon, origin_lat, z.lon, z.lat), 2)
        route = await _osrm_walking_route(origin_lat, origin_lon, z.lat, z.lon)
        results.append({
            "id": z.id,
            "nombre": z.nombre,
            "tipo": z.tipo,
            "distance_straight_km": straight_km,
            "distance_walking_m": route["distance_m"] if route else None,
            "duration_walking_min": route["duration_min"] if route else None,
            "route_geometry": route["geometry"] if route else None,
            "validated": z.validated,
        })

    return {
        "commune_id": commune_id,
        "origin": {"lat": origin_lat, "lon": origin_lon},
        "zones": results,
        "validated": False,
        "disclaimer": (
            "Zonas candidatas de OpenStreetMap (parques/colegios/estadios), sin "
            "validar todavía por Defensoría Civil o DAGRD como puntos de "
            "encuentro oficiales."
        ),
    }


async def main() -> None:
    """Refresca `safe_zones` desde Overpass API:

        cd platform/backend && PYTHONPATH=. python -m alerts.evacuation
    """
    from db.session import AsyncSessionLocal

    logging.basicConfig(level=logging.INFO)
    async with AsyncSessionLocal() as session:
        n = await refresh_safe_zones(session)
    print("zonas_seguras_cargadas", n)


if __name__ == "__main__":
    asyncio.run(main())
