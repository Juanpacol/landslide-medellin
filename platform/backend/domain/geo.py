"""
Pure geometry. No I/O, no external dependencies — just `math`.

Used to live in `infrastructure/external/arcgis_client.py`, which imports
`httpx` and `scraper.common`. Since `domain/` cannot import anything with I/O
(CLAUDE.md's layering rule), keeping the pure functions here is what lets
`domain/seismic_dedup.py` compute distances without dragging an HTTP client
into the domain layer. `arcgis_client` re-exports `haversine_km` so its
existing importers keep working.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distance in km between two points.

    ⚠️ Order is **LON first**, for compatibility with existing callers
    (GeoJSON and ArcGIS use `[lon, lat]`). In Medellín lat≈6.2 and
    lon≈−75.5, so swapping the arguments does NOT raise any error: it
    returns a wrong but plausible distance, the worst possible failure mode.
    If you have lat/lon at hand, use `distance_km`, which is keyword-only.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_km(*, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Same as `haversine_km` but **keyword-only**: the order can't be swapped.

    Use this one in new code.
    """
    return haversine_km(lon1, lat1, lon2, lat2)
