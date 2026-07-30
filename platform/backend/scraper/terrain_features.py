"""
Terrain features per BARRIO (slope, elevation) — a one-off script, not a cron.

Populates `barrio_terrain` (specs/006-neural-estimators/tasks.md's highest-value
remaining data gap: susceptibility coverage stuck at 1 of 5 components because
this table has always been empty). `db/models/barrio_terrain.py`'s docstring
describes populating it from hand-downloaded SRTM/MODIS GeoTIFFs; this script
takes a lighter-weight path instead — Open Topo Data's public SRTM90m API
(https://www.opentopodata.org, no key required) — since no GeoTIFF processing
pipeline (rasterio, GDAL) exists in this project yet.

## Method and its honest limits

For each barrio, elevation is sampled at the centroid plus 4 points offset
~90m north/south/east/west (matching SRTM90m's resolution), and slope is
estimated via finite differences:

    slope_rad = atan(sqrt(((e_N - e_S) / 2dy)² + ((e_E - e_W) / 2dx)²))

This gives ONE slope estimate per barrio, at its centroid — not a true
within-barrio distribution. `slope_mean_deg` and `slope_p90_deg` are both set
to this same value, which is a real gap against
`db/models/barrio_terrain.py`'s stated design (p90 is meant to capture that
"a barrio with one steep slope and one flat area" is not well summarized by
a mean). A proper implementation would sample many points per polygon from a
full DEM raster. This is declared as a proxy, not the target design.

TWI and NDVI are NOT populated by this script: TWI needs flow-accumulation
over a full DEM grid (not point samples), and NDVI needs satellite imagery
access this project doesn't have configured. Both remain None, exactly as
they were before this script ran — no fabricated values.

Usage:

    cd platform/backend && PYTHONPATH=. python -m scraper.terrain_features
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.barrio_terrain import BarrioTerrain
from db.session import AsyncSessionLocal
from scraper.common import log_scrape_run, utcnow

logger = logging.getLogger(__name__)

_DEFAULT_GEOJSON = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "barrios-medellin.json"
)
BARRIOS_GEOJSON = Path(os.getenv("BARRIOS_GEOJSON", str(_DEFAULT_GEOJSON)))

OPENTOPODATA_URL = "https://api.opentopodata.org/v1/srtm90m"
DEM_SOURCE = "opentopodata_srtm90m"

# SRTM90m's native resolution — the finite-difference step matches the grid
# so neighboring samples aren't just noise from interpolation between the
# same underlying pixel.
SAMPLE_OFFSET_M = 90.0
METERS_PER_DEG_LAT = 111_320.0

# Public instance rate limit: 1 request/sec, up to 100 locations/request.
_BATCH_SIZE = 100
_RATE_LIMIT_S = 1.05


def _centroid_lonlat(geometry: dict[str, Any]) -> tuple[float, float] | None:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return None
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = max((poly[0] for poly in coords), key=len)
    else:
        return None
    if not ring:
        return None
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return lon, lat


def _offset_points(lat: float, lon: float, offset_m: float) -> dict[str, tuple[float, float]]:
    """Returns {direction: (lat, lon)} for N/S/E/W points `offset_m` away."""
    dlat = offset_m / METERS_PER_DEG_LAT
    dlon = offset_m / (METERS_PER_DEG_LAT * math.cos(math.radians(lat)))
    return {
        "center": (lat, lon),
        "N": (lat + dlat, lon),
        "S": (lat - dlat, lon),
        "E": (lat, lon + dlon),
        "W": (lat, lon - dlon),
    }


def _slope_deg_from_elevations(elev: dict[str, float | None], offset_m: float) -> float | None:
    """Finite-difference slope at the centroid from its N/S/E/W neighbors."""
    e_n, e_s, e_e, e_w = elev.get("N"), elev.get("S"), elev.get("E"), elev.get("W")
    if None in (e_n, e_s, e_e, e_w):
        return None
    dz_dy = (e_n - e_s) / (2 * offset_m)
    dz_dx = (e_e - e_w) / (2 * offset_m)
    slope_rad = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
    return round(math.degrees(slope_rad), 2)


async def _fetch_elevations(
    client: httpx.AsyncClient, points: list[tuple[float, float]]
) -> list[float | None]:
    """Fetches elevations for up to `_BATCH_SIZE` (lat, lon) points, one API call."""
    locations = "|".join(f"{lat},{lon}" for lat, lon in points)
    r = await client.get(OPENTOPODATA_URL, params={"locations": locations})
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    return [(res.get("elevation") if isinstance(res, dict) else None) for res in results] or [
        None
    ] * len(points)


async def run_terrain_features() -> int:
    started = utcnow()
    status = "error"
    processed = 0
    with_slope = 0
    detail: str | None = None

    async with AsyncSessionLocal() as session:
        try:
            data = json.loads(BARRIOS_GEOJSON.read_text(encoding="utf-8"))
            features = data.get("features") or []
            logger.info("Barrios loaded for terrain sampling: %d", len(features))

            barrios: list[dict[str, Any]] = []
            for feat in features:
                props = feat.get("properties") or {}
                codigo = str(props.get("codigo") or "").strip()
                comuna = str(props.get("comuna") or "").strip()
                centroid = _centroid_lonlat(feat.get("geometry") or {})
                if not codigo or centroid is None:
                    continue
                lon, lat = centroid
                barrios.append({"codigo": codigo, "comuna": comuna or None, "lat": lat, "lon": lon})

            if not barrios:
                raise ValueError("Could not load any valid barrio centroid")

            # Flatten every barrio's 5 sample points into one queue, batched
            # to respect the public API's rate limit and per-request cap.
            queue: list[tuple[str, str, float, float]] = []  # (codigo, direction, lat, lon)
            for b in barrios:
                for direction, (plat, plon) in _offset_points(
                    b["lat"], b["lon"], SAMPLE_OFFSET_M
                ).items():
                    queue.append((b["codigo"], direction, plat, plon))

            elevations: dict[tuple[str, str], float | None] = {}
            async with httpx.AsyncClient(timeout=30.0) as client:
                for i in range(0, len(queue), _BATCH_SIZE):
                    batch = queue[i : i + _BATCH_SIZE]
                    values = await _fetch_elevations(
                        client, [(lat, lon) for *_r, lat, lon in batch]
                    )
                    for (codigo, direction, _lat, _lon), val in zip(batch, values, strict=True):
                        elevations[(codigo, direction)] = val
                    if i + _BATCH_SIZE < len(queue):
                        await asyncio.sleep(_RATE_LIMIT_S)

            for b in barrios:
                codigo = b["codigo"]
                per_dir = {d: elevations.get((codigo, d)) for d in ("center", "N", "S", "E", "W")}
                slope = _slope_deg_from_elevations(per_dir, SAMPLE_OFFSET_M)
                elevation_mean = per_dir.get("center")

                row = {
                    "barrio_codigo": codigo,
                    "commune_id": b["comuna"],
                    "slope_mean_deg": slope,
                    "slope_p90_deg": slope,  # proxy — see module docstring
                    "elevation_mean_m": elevation_mean,
                    "dem_source": DEM_SOURCE if slope is not None else None,
                }
                stmt = (
                    pg_insert(BarrioTerrain)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["barrio_codigo"],
                        set_={
                            "commune_id": row["commune_id"],
                            "slope_mean_deg": row["slope_mean_deg"],
                            "slope_p90_deg": row["slope_p90_deg"],
                            "elevation_mean_m": row["elevation_mean_m"],
                            "dem_source": row["dem_source"],
                        },
                    )
                )
                await session.execute(stmt)
                processed += 1
                if slope is not None:
                    with_slope += 1

            await session.commit()
            status = "ok"
            detail = f"barrios={processed} con_pendiente={with_slope}"
            logger.info("Terrain features done: %s", detail)
        except Exception as exc:  # noqa: BLE001
            detail = repr(exc)
            await session.rollback()
            raise
        finally:
            await log_scrape_run(
                session,
                source="terrain_features",
                status=status,
                run_started_at=started,
                records_downloaded=processed,
                records_valid=with_slope,
                detail=detail,
            )
    return processed


async def main() -> None:
    from observability.logging_config import configure_logging

    configure_logging("scraper-terrain-features")
    n = await run_terrain_features()
    print("barrios_procesados", n)


if __name__ == "__main__":
    asyncio.run(main())
