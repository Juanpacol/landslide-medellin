"""
Cliente OSRM (servidor demo público de project-osrm.org) — rutas a pie.

Transporte puro; la selección de zonas seguras y el fallback a distancia en
línea recta siguen en alerts/evacuation.py.
"""

from __future__ import annotations

import logging
from typing import Any

from scraper.common import httpx_client

logger = logging.getLogger(__name__)

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/foot"


async def walking_route(
    origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
) -> dict[str, Any] | None:
    """Ruta caminando origen→destino. None si OSRM no responde (el caller
    decide el fallback)."""
    url = f"{OSRM_BASE_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    try:
        async with httpx_client(timeout=15.0) as client:
            response = await client.get(url, params={"overview": "full", "geometries": "geojson"})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSRM no disponible (%s); se devuelve distancia en línea recta", exc)
        return None

    routes = data.get("routes") or []
    if not routes:
        return None
    route = routes[0]
    return {
        "distance_m": route.get("distance"),
        "duration_min": round(route.get("duration", 0) / 60, 1),
        "geometry": route.get("geometry"),
    }
