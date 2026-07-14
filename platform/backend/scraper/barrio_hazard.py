"""
Amenaza por movimientos en masa a nivel de BARRIO (script puntual, no cron).

Muestrea el centroide de cada uno de los ~401 barrios de
`platform/frontend/lib/barrios-medellin.json` contra la capa oficial de
ordenamiento territorial VM_05_Amenazas_Movimientos_Masa (la misma que
scraper/medellin_datos.py ya consulta, pero solo en los 21 centroides de
comuna). El resultado (`grado_amenaza` por barrio) se upserta en la tabla
`barrio_hazard` que sirve `GET /api/risk/barrios-hazard` para colorear la
capa de barrios del mapa.

La cartografía cambia en meses/años: correr a mano cuando haga falta:

    cd platform/backend && PYTHONPATH=. python -m scraper.barrio_hazard
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.barrio_hazard import BarrioHazard
from db.session import AsyncSessionLocal
from scraper.common import httpx_client, log_scrape_run, utcnow
from scraper.medellin_datos import VM05_BASE, _query_point_layer

logger = logging.getLogger(__name__)

# El GeoJSON vive en el frontend (lo consume el mapa); este script se corre
# desde el repo, así que se resuelve por ruta relativa (override por env var).
_DEFAULT_GEOJSON = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "barrios-medellin.json"
BARRIOS_GEOJSON = Path(os.getenv("BARRIOS_GEOJSON", str(_DEFAULT_GEOJSON)))

_CONCURRENCY = 8


def _centroid_lonlat(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """Centroide simple (promedio del anillo exterior) de Polygon/MultiPolygon GeoJSON."""
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


async def _hazard_for_point(client, sem: asyncio.Semaphore, lon: float, lat: float) -> str | None:
    async with sem:
        try:
            feats = await _query_point_layer(client, VM05_BASE, 2, lon, lat)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Consulta VM05 falló para (%.4f, %.4f): %s", lon, lat, exc)
            return None
    if not feats:
        return None
    return (feats[0].get("attributes") or {}).get("grado_amenaza")


async def run_barrio_hazard() -> int:
    started = utcnow()
    status = "error"
    processed = 0
    with_hazard = 0
    detail: str | None = None

    async with AsyncSessionLocal() as session:
        try:
            data = json.loads(BARRIOS_GEOJSON.read_text(encoding="utf-8"))
            features = data.get("features") or []
            logger.info("Barrios en el GeoJSON: %d", len(features))

            sem = asyncio.Semaphore(_CONCURRENCY)
            async with httpx_client() as client:

                async def _process(feat: dict[str, Any]) -> dict[str, Any] | None:
                    props = feat.get("properties") or {}
                    codigo = str(props.get("codigo") or "").strip()
                    nombre = str(props.get("nombre") or "").strip()
                    comuna = str(props.get("comuna") or "").strip()
                    if not codigo or not nombre:
                        return None
                    centroid = _centroid_lonlat(feat.get("geometry") or {})
                    if centroid is None:
                        return None
                    hazard = await _hazard_for_point(client, sem, *centroid)
                    return {
                        "barrio_codigo": codigo,
                        "nombre": nombre,
                        "commune_id": comuna or "s/d",
                        "hazard_grade": hazard,
                    }

                results = await asyncio.gather(*(_process(f) for f in features))

            for row in results:
                if row is None:
                    continue
                stmt = (
                    pg_insert(BarrioHazard)
                    .values(**row)
                    .on_conflict_do_update(
                        index_elements=["barrio_codigo"],
                        set_={
                            "nombre": row["nombre"],
                            "commune_id": row["commune_id"],
                            "hazard_grade": row["hazard_grade"],
                        },
                    )
                )
                await session.execute(stmt)
                processed += 1
                if row["hazard_grade"]:
                    with_hazard += 1

            await session.commit()
            status = "ok"
            detail = f"barrios={processed} con_amenaza={with_hazard}"
            logger.info("Barrio hazard listo: %s", detail)
        except Exception as exc:  # noqa: BLE001
            detail = repr(exc)
            await session.rollback()
            raise
        finally:
            await log_scrape_run(
                session,
                source="barrio_hazard",
                status=status,
                run_started_at=started,
                records_downloaded=processed,
                records_valid=with_hazard,
                detail=detail,
            )
    return processed


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    n = await run_barrio_hazard()
    print("barrios_procesados", n)


if __name__ == "__main__":
    asyncio.run(main())
