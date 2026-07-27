"""
Validar eventos históricos reales (`landslide_events`) contra lo que el
Snake Line (SWI × lluvia) hubiera clasificado ese día, usando datos de lluvia
ya backfilleados por `scraper/historical_backfill.py` (fuentes
`historical_siata`/`historical_ideam` en `MLFeature.features`).

Reutiliza directamente `ml.soil_water_index.compute_swi` y
`alerts.snake_line.classify_point` — NO reimplementa la fórmula, para que
cualquier ajuste de parámetros (drain_rate, slope, intercept) se refleje aquí
sin duplicar lógica.

Limitación honesta: el backfill histórico solo tiene lluvia DIARIA (suma del
día), no la ventana de 60 minutos que usa Snake Line en producción. Se usa la
lluvia del día del evento como proxy de "y" — más ruidoso que el dato en
vivo, pero es lo único disponible para fechas pasadas. Se documenta en el
output, no se presenta como equivalente al Snake Line en tiempo real.

Uso:

    cd platform/backend && PYTHONPATH=. python -m scraper.validar_eventos_historicos
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from alerts.snake_line import CRITICAL_LINES, classify_point
from db.models.landslide_event import LandslideEvent
from db.models.ml_feature import MLFeature
from db.session import AsyncSessionLocal
from ml.soil_water_index import DRAIN_RATE_DEFAULT, compute_swi

logger = logging.getLogger(__name__)

HISTORICAL_RAIN_SOURCES = ("historical_siata", "historical_ideam")
SWI_LOOKBACK_DAYS = 30


def _parse_event_date(fecha: str | None) -> date | None:
    if not fecha:
        return None
    try:
        return datetime.fromisoformat(fecha[:10]).date()
    except ValueError:
        return None


async def _daily_rain_by_commune(session) -> dict[str, dict[date, float]]:
    """Reconstruye lluvia diaria por comuna desde el backfill histórico
    (`MLFeature.features->>'precip_sum_mm_day'`, fuentes historical_siata /
    historical_ideam). Es la única fuente con cobertura para fechas pasadas."""
    rows = (await session.execute(select(MLFeature))).scalars().all()
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for row in rows:
        feats = row.features or {}
        if feats.get("source") not in HISTORICAL_RAIN_SOURCES:
            continue
        if row.commune_id is None or row.reference_date is None:
            continue
        d = row.reference_date
        d = d.astimezone(timezone.utc).date() if d.tzinfo else d.date()
        precip = feats.get("precip_sum_mm_day")
        if precip is None:
            continue
        out[str(row.commune_id)][d] = out[str(row.commune_id)].get(d, 0.0) + float(precip)
    return out


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async with AsyncSessionLocal() as session:
        events = (await session.execute(select(LandslideEvent))).scalars().all()
        if not events:
            logger.error("Sin eventos en landslide_events. Ejecuta primero:")
            logger.error("  python -m scraper.historical_backfill")
            return

        daily_rain_by_commune = await _daily_rain_by_commune(session)

    resultados = []
    for ev in events:
        d = _parse_event_date(ev.fecha)
        cid = str(ev.commune_id) if ev.commune_id is not None else None

        if d is None or cid is None:
            resultados.append(
                {
                    "evento_id": ev.id,
                    "commune_id": cid,
                    "fecha": ev.fecha,
                    "fuente": ev.source_row_id,
                    "evaluable": False,
                    "motivo": "sin fecha" if d is None else "sin commune_id",
                }
            )
            continue

        daily_rain = daily_rain_by_commune.get(cid)
        if not daily_rain:
            resultados.append(
                {
                    "evento_id": ev.id,
                    "commune_id": cid,
                    "fecha": d.isoformat(),
                    "fuente": ev.source_row_id,
                    "evaluable": False,
                    "motivo": "sin lluvia histórica para esa comuna",
                }
            )
            continue

        swi = compute_swi(
            daily_rain, d, drain_rate=DRAIN_RATE_DEFAULT, window_days=SWI_LOOKBACK_DAYS
        )
        y_rain_day_proxy = daily_rain.get(d, 0.0)
        status = classify_point(swi, y_rain_day_proxy, cid)

        resultados.append(
            {
                "evento_id": ev.id,
                "commune_id": cid,
                "fecha": d.isoformat(),
                "fuente": ev.source_row_id,
                "evaluable": True,
                "swi_pct": swi,
                "lluvia_dia_evento_mm": round(y_rain_day_proxy, 2),
                "snake_line_status": status,
                "hubiera_alertado": status in ("AMARILLO", "ROJO"),
            }
        )

    df = pd.DataFrame(resultados)
    evaluables = df[df["evaluable"] == True] if not df.empty else df

    logger.info("=" * 70)
    logger.info("VALIDACIÓN: EVENTOS HISTÓRICOS vs SNAKE LINE")
    logger.info("=" * 70)
    logger.info(f"Total eventos en landslide_events: {len(df)}")
    logger.info(f"Evaluables (fecha + commune_id + lluvia histórica): {len(evaluables)}")

    if len(evaluables) == 0:
        logger.warning("\nNinguno evaluable todavía. Causas más comunes:")
        if not df.empty:
            logger.warning(df["motivo"].value_counts().to_string())
        logger.warning(
            "\nEjecuta en orden: historical_backfill.py → geocode_events.py → este script."
        )
        return

    aciertos = int(evaluables["hubiera_alertado"].sum())
    total = len(evaluables)
    tasa = aciertos / total * 100

    logger.info(f"\nHubiera alertado (AMARILLO/ROJO): {aciertos}/{total} ({tasa:.1f}%)")
    logger.info("\nDistribución de status:")
    logger.info(evaluables["snake_line_status"].value_counts().to_string())

    logger.info(
        f"\nParámetros evaluados: drain_rate={DRAIN_RATE_DEFAULT}, línea crítica={CRITICAL_LINES['default']}"
    )
    logger.info(
        "(y = lluvia del día del evento, proxy de la ventana de 60min que usa Snake Line en vivo)"
    )

    if tasa < 60:
        logger.warning(
            f"\n⚠️ Tasa baja ({tasa:.1f}%). Considerar: subir drain_rate o bajar intercept en alerts/snake_line.py"
        )
    elif tasa > 90:
        logger.info(
            f"\n✅ Tasa alta ({tasa:.1f}%) — revisar que no sea por proxy de lluvia diaria demasiado laxo."
        )
    else:
        logger.info(f"\n🟡 Tasa razonable ({tasa:.1f}%).")

    out_path = Path(__file__).resolve().parents[1] / "validacion_eventos.csv"
    df.to_csv(out_path, index=False)
    logger.info(f"\nDetalle guardado en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
