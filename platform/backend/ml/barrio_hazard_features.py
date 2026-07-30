"""
ML feature for barrio → commune hazard coherence.

The model predicts at commune level, but the official geomorphological
hazard (VM_05, `db/models/barrio_hazard.py`) is already sampled at barrio
level (~401 polygons). Without this feature, the model "doesn't know" that
one commune has several barrios in Alta hazard while another has none — two
communes with the same rain got the same risk despite very different
geomorphology.

This module summarizes that information into one scalar per commune:

    pct_barrios_alta_amenaza = barrios with hazard_grade "Alta" / total barrios with data

Doesn't replace a real per-barrio prediction (that would need per-barrio
historical series, which don't exist); it's the statistical bridge available
today.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.barrio_hazard import BarrioHazard

FEATURE_KEY = "pct_barrios_alta_amenaza"


async def pct_barrios_alta_amenaza(session: AsyncSession) -> dict[str, float]:
    """% of barrios with 'Alta' hazard per commune (0.0-1.0). Communes with
    no barrio data at all don't appear in the result (no 0 is invented)."""
    rows = (await session.execute(select(BarrioHazard))).scalars().all()

    with_data: dict[str, int] = {}
    with_alta: dict[str, int] = {}
    for r in rows:
        if not r.hazard_grade:
            continue
        cid = r.commune_id
        with_data[cid] = with_data.get(cid, 0) + 1
        if "alta" in r.hazard_grade.strip().lower():
            with_alta[cid] = with_alta.get(cid, 0) + 1

    return {
        cid: round(with_alta.get(cid, 0) / total, 4)
        for cid, total in with_data.items()
        if total > 0
    }
