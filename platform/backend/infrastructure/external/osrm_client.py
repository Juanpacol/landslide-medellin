"""
OSRM client (project-osrm.org's public demo server) — walking routes.

Pure transport; safe-zone selection and the straight-line-distance fallback
stay in alerts/evacuation.py.
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
    """Walking route origin→destination. None if OSRM doesn't respond (the
    caller decides the fallback)."""
    url = f"{OSRM_BASE_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    try:
        async with httpx_client(timeout=15.0) as client:
            response = await client.get(url, params={"overview": "full", "geometries": "geojson"})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSRM unavailable (%s); falling back to straight-line distance", exc)
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
