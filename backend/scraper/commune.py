from __future__ import annotations

import math
import re
from typing import Any

import httpx

from scraper.common import with_retries

COMUNA_QUERY_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11/query"
)

_CORREG_TO_ML = {"50": "17", "60": "18", "70": "19", "80": "20", "90": "21"}


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
    if n in (50, 60, 70, 80, 90):
        return _CORREG_TO_ML.get(str(n))
    return None


async def lookup_commune_for_point(client: httpx.AsyncClient, lon: float, lat: float) -> dict[str, Any]:
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


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))
