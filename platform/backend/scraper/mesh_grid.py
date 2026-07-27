"""
Mesh Maps — cuadrículas de ~1.5km sobre Medellín (metodología JMA).

Script puntual (cartografía casi estática, se corre a mano cuando cambien
los barrios o su amenaza — no es un cron):

    cd platform/backend && PYTHONPATH=. python -m scraper.mesh_grid

Divide el área cubierta por los 401 barrios de `barrios-medellin.json` en
cuadrículas cuadradas de ~1.5km de lado (en vez de las 21 comunas, que diluyen
el riesgo real de laderas específicas) y hereda para cada cuadrícula:
- Las comunas y barrios que intersecta.
- El peor `hazard_grade` (VM05) entre sus barrios.

LÍMITE HONESTO: el riesgo de cada cuadrícula se hereda del modelo a nivel
comuna (no hay sensores ni predicción por cuadrícula) — el valor de esta capa
es visualización más precisa y evacuación dirigida, no predicción más
granular. Se marca `risk_source: "inherited_from_commune"` en el endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

from shapely.geometry import box, shape
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.barrio_hazard import BarrioHazard
from db.models.mesh_quadrant import MeshQuadrant
from db.session import AsyncSessionLocal
from scraper.common import log_scrape_run, utcnow

logger = logging.getLogger(__name__)

_DEFAULT_GEOJSON = (
    Path(__file__).resolve().parents[2] / "frontend" / "lib" / "barrios-medellin.json"
)
BARRIOS_GEOJSON = Path(os.getenv("BARRIOS_GEOJSON", str(_DEFAULT_GEOJSON)))

GRID_SIZE_KM = 1.5
MEDELLIN_LAT_REF = 6.24  # para convertir km -> grados de longitud

_HAZARD_RANK: dict[str, int] = {"alta": 3, "media": 2, "baja": 1, "muy baja": 0}


def _worst_hazard(grades: list[str]) -> str | None:
    ranked = [g for g in grades if g]
    if not ranked:
        return None
    return max(ranked, key=lambda g: _HAZARD_RANK.get(g.strip().lower(), -1))


def _km_to_degrees(km: float, lat_ref: float) -> tuple[float, float]:
    """(delta_lat_deg, delta_lon_deg) equivalentes a `km` en esa latitud."""
    lat_deg = km / 111.32
    lon_deg = km / (111.32 * math.cos(math.radians(lat_ref)))
    return lat_deg, lon_deg


def _build_grid(
    bounds: tuple[float, float, float, float], grid_size_km: float
) -> list[dict[str, Any]]:
    """bounds = (minx, miny, maxx, maxy) en lon/lat. Genera cuadrículas cuadradas."""
    minx, miny, maxx, maxy = bounds
    lat_step, lon_step = _km_to_degrees(grid_size_km, MEDELLIN_LAT_REF)

    quads = []
    quad_id = 0
    lat = miny
    while lat < maxy:
        lon = minx
        while lon < maxx:
            quads.append(
                {
                    "id": f"Q_{quad_id:04d}",
                    "geometry": box(lon, lat, lon + lon_step, lat + lat_step),
                }
            )
            quad_id += 1
            lon += lon_step
        lat += lat_step
    return quads


async def run_mesh_grid() -> int:
    started = utcnow()
    status = "error"
    processed = 0
    with_hazard = 0
    detail: str | None = None

    async with AsyncSessionLocal() as session:
        try:
            data = json.loads(BARRIOS_GEOJSON.read_text(encoding="utf-8"))
            features = data.get("features") or []
            logger.info("Barrios cargados para el grid: %d", len(features))

            barrio_geoms: list[dict[str, Any]] = []
            all_bounds: list[tuple[float, float, float, float]] = []
            for feat in features:
                props = feat.get("properties") or {}
                codigo = str(props.get("codigo") or "").strip()
                comuna = str(props.get("comuna") or "").strip()
                geom_raw = feat.get("geometry")
                if not codigo or not geom_raw:
                    continue
                try:
                    geom = shape(geom_raw)
                except Exception:  # noqa: BLE001
                    continue
                if geom.is_empty:
                    continue
                barrio_geoms.append({"codigo": codigo, "comuna": comuna or "s/d", "geom": geom})
                all_bounds.append(geom.bounds)

            if not barrio_geoms:
                raise ValueError("No se pudo cargar ningún polígono de barrio válido")

            minx = min(b[0] for b in all_bounds)
            miny = min(b[1] for b in all_bounds)
            maxx = max(b[2] for b in all_bounds)
            maxy = max(b[3] for b in all_bounds)

            hazard_by_codigo: dict[str, str | None] = {
                r.barrio_codigo: r.hazard_grade
                for r in (await session.execute(select(BarrioHazard))).scalars().all()
            }

            quads = _build_grid((minx, miny, maxx, maxy), GRID_SIZE_KM)
            logger.info("Cuadrículas generadas: %d", len(quads))

            for quad in quads:
                q_geom = quad["geometry"]
                intersecting = [b for b in barrio_geoms if q_geom.intersects(b["geom"])]
                if not intersecting:
                    continue

                commune_ids = sorted({b["comuna"] for b in intersecting})
                barrio_codigos = sorted({b["codigo"] for b in intersecting})
                grades = [hazard_by_codigo.get(b["codigo"]) for b in intersecting]
                worst = _worst_hazard([g for g in grades if g])
                n_alta = sum(1 for g in grades if g and g.strip().lower() == "alta")

                row = {
                    "id": quad["id"],
                    "geometry": json.loads(json.dumps(q_geom.__geo_interface__)),
                    "commune_ids": commune_ids,
                    "barrio_codigos": barrio_codigos,
                    "hazard_grade": worst,
                    "n_barrios_alta": n_alta,
                }
                stmt = (
                    pg_insert(MeshQuadrant)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "geometry": row["geometry"],
                            "commune_ids": row["commune_ids"],
                            "barrio_codigos": row["barrio_codigos"],
                            "hazard_grade": row["hazard_grade"],
                            "n_barrios_alta": row["n_barrios_alta"],
                        },
                    )
                )
                await session.execute(stmt)
                processed += 1
                if worst:
                    with_hazard += 1

            await session.commit()
            status = "ok"
            detail = f"cuadriculas={processed} con_amenaza={with_hazard}"
            logger.info("Mesh grid listo: %s", detail)
        except Exception as exc:  # noqa: BLE001
            detail = repr(exc)
            await session.rollback()
            raise
        finally:
            await log_scrape_run(
                session,
                source="mesh_grid",
                status=status,
                run_started_at=started,
                records_downloaded=processed,
                records_valid=with_hazard,
                detail=detail,
            )
    return processed


async def main() -> None:
    from observability.logging_config import configure_logging

    configure_logging("scraper-mesh-grid")
    n = await run_mesh_grid()
    print("cuadriculas_procesadas", n)


if __name__ == "__main__":
    asyncio.run(main())
