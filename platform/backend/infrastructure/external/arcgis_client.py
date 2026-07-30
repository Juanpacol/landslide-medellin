"""
Medellín's ArcGIS map server client + geo utilities.

Moved from scraper/commune.py (which re-exports for compatibility: every
scraper and ml/seismic_features import from there). The official-code →
canonical-id mapping is derived from domain/communes.py, not duplicated.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from domain.communes import COMMUNES

# Re-exported: `haversine_km` used to live here, but it's PURE geometry and
# now lives in `domain/geo.py`, so the domain layer can use it without
# dragging in httpx. Still exposed from here because several modules import
# it from this path (`ml/seismic_features.py`, `alerts/evacuation.py`).
from domain.geo import distance_km, haversine_km
from scraper.common import with_retries

COMUNA_QUERY_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11/query"
)

# Official corregimiento code → canonical id, derived from the single source.
_CORREG_TO_ML: dict[str, str] = {
    c.official_code: c.id for c in COMMUNES if c.tipo == "corregimiento"
}


def official_to_ml_commune(codigo: str | None, subtipo: int | None) -> str | None:
    if not codigo:
        return None
    if codigo.startswith("SN"):
        return None
    if subtipo == 2 or codigo in _CORREG_TO_ML:
        return _CORREG_TO_ML.get(codigo, codigo)
    digits = codigo.strip()
    if digits.isdigit():
        return str(int(digits))
    m = re.match(r"^0*(\d+)$", digits)
    return str(int(m.group(1))) if m else codigo


def parse_ml_commune_from_siata_field(comuna_raw: str) -> str | None:
    if not comuna_raw or not comuna_raw.strip():
        return None
    m = re.search(r"(\d{1,2})", comuna_raw)
    if not m:
        return None
    n = int(m.group(1))
    if 1 <= n <= 16:
        return str(n)
    if str(n) in _CORREG_TO_ML:
        return _CORREG_TO_ML[str(n)]
    return None


async def lookup_commune_for_point(
    client: httpx.AsyncClient, lon: float, lat: float
) -> dict[str, Any]:
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "codigo,nombre,identificacion,subtipo_comunacorregimiento",
        "returnGeometry": "false",
        "f": "json",
    }

    async def _call() -> dict[str, Any]:
        r = await client.get(COMUNA_QUERY_URL, params=params)
        r.raise_for_status()
        return r.json()

    data = await with_retries(_call)
    feats = data.get("features") or []
    if not feats:
        return {"ml_commune_id": None, "raw": None}
    attrs = feats[0].get("attributes") or {}
    codigo = attrs.get("codigo")
    subtipo = attrs.get("subtipo_comunacorregimiento")
    ml = official_to_ml_commune(str(codigo) if codigo is not None else None, subtipo)
    return {"ml_commune_id": ml, "raw": attrs}


def ring_centroid_lonlat(rings: list[list[list[float]]]) -> tuple[float, float]:
    ring = rings[0]
    sx = sum(p[0] for p in ring)
    sy = sum(p[1] for p in ring)
    n = max(len(ring), 1)
    return sx / n, sy / n


__all__ = [
    "COMUNA_QUERY_URL",
    "distance_km",
    "haversine_km",
    "lookup_commune_for_point",
    "official_to_ml_commune",
    "parse_ml_commune_from_siata_field",
    "ring_centroid_lonlat",
]
