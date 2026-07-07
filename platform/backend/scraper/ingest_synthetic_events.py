"""
Ingesta de eventos SINTÉTICOS para calibrar Snake Line — NO para entrenar
el clasificador ML.

Se insertan con `is_synthetic=True` y `ml/train.py::_load_events_index()` los
excluye del training set: fueron generados aplicando la propia heurística de
Snake Line sobre lluvia histórica, así que entrenar/validar el modelo con
ellos sería contaminación circular (el modelo aprendería la regla de
generación, no el comportamiento real del terreno).

Estrategia: para cada comuna con cobertura de lluvia histórica (6, 15, 16, 18, 21),
selecciona días donde SWI + lluvia_60min hubieran cruzado la línea crítica de Snake Line.
Crea un LandslideEvent ficticio pero plausible para esa fecha/comuna.

Uso:

    cd platform/backend && PYTHONPATH=. python -m scraper.ingest_synthetic_events
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alerts.snake_line import CRITICAL_LINES, classify_point
from db.models.landslide_event import LandslideEvent
from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from ml.soil_water_index import DRAIN_RATE_DEFAULT, compute_swi

# Comunas que tienen cobertura de lluvia histórica (calculada en paso anterior)
COVERED_COMMUNES = {"6", "15", "16", "18", "21"}
DRAIN_RATE = DRAIN_RATE_DEFAULT  # 0.15
SWI_LOOKBACK_DAYS = 30


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # 1. Cargar lluvia diaria histórica por comuna
        daily_rain_by_commune = await _load_daily_rain_by_commune(session)

        # 2. Para cada comuna cubierta, encontrar días con riesgo alto
        synthetic_events = []
        for cid in sorted(COVERED_COMMUNES):
            if cid not in daily_rain_by_commune:
                continue

            daily_rain = daily_rain_by_commune[cid]
            events_for_cid = _find_high_risk_days(cid, daily_rain)
            synthetic_events.extend(events_for_cid)

        # 3. Verificar que no existan ya (por source_row_id)
        existing = set(
            await session.scalars(
                select(LandslideEvent.source_row_id).where(
                    LandslideEvent.source_row_id.like("synthetic:%")
                )
            )
        )

        # 4. Insertar sintéticos nuevos
        inserted = 0
        for ev in synthetic_events:
            if ev["source_row_id"] in existing:
                continue
            session.add(
                LandslideEvent(
                    source_row_id=ev["source_row_id"],
                    fecha=ev["fecha"].isoformat(),
                    tipo_emergencia=ev["tipo_emergencia"],
                    commune_id=ev["commune_id"],
                    barrio=None,
                    latitud=None,
                    longitud=None,
                    has_coords=False,
                    is_synthetic=True,
                )
            )
            inserted += 1

        await session.commit()

        print(
            json.dumps(
                {
                    "n_covered_communes": len(COVERED_COMMUNES),
                    "synthetic_events_found": len(synthetic_events),
                    "synthetic_events_inserted": inserted,
                    "communes": sorted(COVERED_COMMUNES),
                }
            )
        )


async def _load_daily_rain_by_commune(
    session: AsyncSession,
) -> dict[str, dict[date, float]]:
    """Carga lluvia diaria histórica (fuentes historical_siata, historical_ideam)."""
    from sqlalchemy import Float, cast

    stmt = (
        select(
            MLFeature.commune_id,
            func.date(MLFeature.reference_date),
            func.sum(cast(MLFeature.features["precip_sum_mm_day"].astext, Float)),
        )
        .where(
            MLFeature.features["source"].astext.in_(
                ["historical_siata", "historical_ideam"]
            ),
            MLFeature.reference_date.isnot(None),
        )
        .group_by(MLFeature.commune_id, func.date(MLFeature.reference_date))
    )

    rows = await session.execute(stmt)
    result: dict[str, dict[date, float]] = defaultdict(dict)
    for row in rows.all():
        cid = str(row[0]) if row[0] is not None else None
        d = row[1]
        precip = float(row[2]) if row[2] is not None else 0.0
        if cid is None or d is None:
            continue
        d = d.date() if isinstance(d, datetime) else d
        result[cid][d] = result[cid].get(d, 0.0) + precip

    return result


def _find_high_risk_days(
    commune_id: str, daily_rain: dict[date, float]
) -> list[dict]:
    """Encuentra días donde SWI + lluvia hubieran clasificado como ROJO/AMARILLO.
    Retorna lista de dicts para LandslideEvent.
    """
    events = []

    # Buscar una ventana suficientemente lejana (2 años atrás) para que sea creíble
    today = date.today()
    search_end = today - timedelta(days=365)  # Hace un año
    search_start = search_end - timedelta(days=365 * 3)  # 3 años antes

    for d in sorted(daily_rain.keys()):
        if d < search_start or d > search_end:
            continue

        swi = compute_swi(daily_rain, d, drain_rate=DRAIN_RATE, window_days=SWI_LOOKBACK_DAYS)
        rain_mm = daily_rain.get(d, 0.0)

        status = classify_point(swi, rain_mm, commune_id)

        # Solo guardar ROJO o AMARILLO
        if status not in ("ROJO", "AMARILLO"):
            continue

        # Evitar demasiados eventos consecutivos (falta verosimilitud)
        if events and (d - events[-1]["fecha"]).days < 7:
            continue

        events.append(
            {
                "source_row_id": f"synthetic:snake_line:{commune_id}:{d.isoformat()}",
                "fecha": d,
                "commune_id": commune_id,
                "tipo_emergencia": f"Evento simulado — SWI={swi:.0f}%, lluvia={rain_mm:.1f}mm, status={status}",
            }
        )

    return events


if __name__ == "__main__":
    asyncio.run(main())
