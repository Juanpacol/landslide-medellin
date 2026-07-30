"""
Validates real historical events (`landslide_events`) against what Snake
Line (SWI × rain) would have classified that day, using rain data already
backfilled by `scraper/historical_backfill.py` (`historical_siata`/
`historical_ideam` sources in `MLFeature.features`).

Reuses `ml.soil_water_index.compute_swi` and `alerts.snake_line.classify_point`
directly — does NOT reimplement the formula, so any parameter adjustment
(drain_rate, slope, intercept) is reflected here without duplicating logic.

Honest limitation: the historical backfill only has DAILY rain (day's sum),
not the 60-minute window Snake Line uses in production. The event day's
rain is used as a proxy for "y" — noisier than the live data, but it's the
only thing available for past dates. Documented in the output, not
presented as equivalent to real-time Snake Line.

Usage:

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
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _daily_rain_by_commune(session: AsyncSession) -> dict[str, dict[date, float]]:
    """Reconstructs daily rain per commune from the historical backfill
    (`MLFeature.features->>'precip_sum_mm_day'`, historical_siata /
    historical_ideam sources). The only source with coverage for past dates."""
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
    """Validate historical landslide events against the Snake Line heuristic and report results."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async with AsyncSessionLocal() as session:
        events = (await session.execute(select(LandslideEvent))).scalars().all()
        if not events:
            logger.error("No events in landslide_events. Run first:")
            logger.error("  python -m scraper.historical_backfill")
            return

        daily_rain_by_commune = await _daily_rain_by_commune(session)

    results = []
    for ev in events:
        d = _parse_event_date(ev.fecha)
        cid = str(ev.commune_id) if ev.commune_id is not None else None

        if d is None or cid is None:
            results.append(
                {
                    "evento_id": ev.id,
                    "commune_id": cid,
                    "fecha": ev.fecha,
                    "fuente": ev.source_row_id,
                    "evaluable": False,
                    "motivo": "no date" if d is None else "no commune_id",
                }
            )
            continue

        daily_rain = daily_rain_by_commune.get(cid)
        if not daily_rain:
            results.append(
                {
                    "evento_id": ev.id,
                    "commune_id": cid,
                    "fecha": d.isoformat(),
                    "fuente": ev.source_row_id,
                    "evaluable": False,
                    "motivo": "no historical rain for that commune",
                }
            )
            continue

        swi = compute_swi(
            daily_rain, d, drain_rate=DRAIN_RATE_DEFAULT, window_days=SWI_LOOKBACK_DAYS
        )
        y_rain_day_proxy = daily_rain.get(d, 0.0)
        status = classify_point(swi, y_rain_day_proxy, cid)

        results.append(
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

    df = pd.DataFrame(results)
    evaluable_rows = df[df["evaluable"]] if not df.empty else df

    logger.info("=" * 70)
    logger.info("VALIDATION: HISTORICAL EVENTS vs SNAKE LINE")
    logger.info("=" * 70)
    logger.info(f"Total events in landslide_events: {len(df)}")
    logger.info(f"Evaluable (date + commune_id + historical rain): {len(evaluable_rows)}")

    if len(evaluable_rows) == 0:
        logger.warning("\nNone evaluable yet. Most common causes:")
        if not df.empty:
            logger.warning(df["motivo"].value_counts().to_string())
        logger.warning("\nRun in order: historical_backfill.py → geocode_events.py → this script.")
        return

    hits = int(evaluable_rows["hubiera_alertado"].sum())
    total = len(evaluable_rows)
    rate = hits / total * 100

    logger.info(f"\nWould have alerted (AMARILLO/ROJO): {hits}/{total} ({rate:.1f}%)")
    logger.info("\nStatus distribution:")
    logger.info(evaluable_rows["snake_line_status"].value_counts().to_string())

    logger.info(
        f"\nParameters evaluated: drain_rate={DRAIN_RATE_DEFAULT}, critical line={CRITICAL_LINES['default']}"
    )
    logger.info("(y = the event day's rain, a proxy for the 60min window live Snake Line uses)")

    if rate < 60:
        logger.warning(
            f"\n⚠️ Low rate ({rate:.1f}%). Consider: raising drain_rate or lowering intercept in alerts/snake_line.py"
        )
    elif rate > 90:
        logger.info(
            f"\n✅ High rate ({rate:.1f}%) — check it isn't from too loose a daily-rain proxy."
        )
    else:
        logger.info(f"\n🟡 Reasonable rate ({rate:.1f}%).")

    out_path = Path(__file__).resolve().parents[1] / "validacion_eventos.csv"
    df.to_csv(out_path, index=False)
    logger.info(f"\nDetail saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
