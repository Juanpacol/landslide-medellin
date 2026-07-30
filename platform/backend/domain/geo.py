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


# Below this, a reading doesn't distinguish "the gauge is dry" from "the gauge is off" — treated
# as inactive so it can't drag an inverse-distance average toward zero (audit finding 2,
# docs/research/audit-2026-07.md §4: averaging in ~180/228 zeroed stations diluted a real signal
# down to 0.003mm).
MIN_ACTIVE_PRECIP_MM = 0.1

# Fewer valid stations than this and the reading isn't trustworthy enough to report — the caller
# must treat it as "no signal" (e.g. skip the snapshot), not silently emit a number.
MIN_STATIONS_FOR_IDW = 2

# A station within this many meters of the commune centroid is treated as "at" it — its weight
# would otherwise blow up as distance approaches 0.
_COINCIDENT_STATION_KM = 0.01


def idw_precip(
    station_points: list[tuple[float, float, float]], *, centroid_lat: float, centroid_lon: float
) -> float | None:
    """Inverse-distance-weighted rainfall at a commune's centroid from its stations' readings.

    `station_points` is `[(lat, lon, precip_mm), ...]`. Stations at or below
    `MIN_ACTIVE_PRECIP_MM` are dropped before weighting — a healthy network has some dry
    stations, but including them in a per-commune average is exactly the aggregation bug that
    zeroed out the trigger (audit finding 2). Weight is `1 / distance_km**2`; a station
    coincident with the centroid (within `_COINCIDENT_STATION_KM`) short-circuits to its own
    reading rather than dividing by ~zero.

    Returns `None` if fewer than `MIN_STATIONS_FOR_IDW` stations remain after filtering — the
    caller must treat that as "insufficient signal", never as `0.0`.
    """
    active = [(lat, lon, val) for lat, lon, val in station_points if val > MIN_ACTIVE_PRECIP_MM]
    if len(active) < MIN_STATIONS_FOR_IDW:
        return None

    weighted_sum = 0.0
    weight_total = 0.0
    for lat, lon, val in active:
        d = distance_km(lat1=lat, lon1=lon, lat2=centroid_lat, lon2=centroid_lon)
        if d <= _COINCIDENT_STATION_KM:
            return val
        w = 1.0 / (d**2)
        weighted_sum += w * val
        weight_total += w

    return weighted_sum / weight_total if weight_total > 0 else None
