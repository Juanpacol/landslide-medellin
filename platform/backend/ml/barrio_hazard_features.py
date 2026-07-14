"""
Feature ML de coherencia barrio → comuna.

El modelo predice a nivel de comuna, pero la amenaza geomorfológica oficial
(VM_05, `db/models/barrio_hazard.py`) ya está muestreada a nivel de barrio
(~401 polígonos). Sin este feature, el modelo "no sabe" que una comuna tiene
varios barrios en amenaza Alta mientras otra no tiene ninguno — dos comunas
con la misma lluvia recibían el mismo riesgo pese a tener geomorfología muy
distinta.

Este módulo resume esa información en un escalar por comuna:

    pct_barrios_alta_amenaza = barrios con hazard_grade "Alta" / total barrios con dato

No sustituye una predicción real por barrio (eso requeriría series históricas
por barrio, que no existen); es el puente estadístico disponible hoy.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.barrio_hazard import BarrioHazard

FEATURE_KEY = "pct_barrios_alta_amenaza"


async def pct_barrios_alta_amenaza(session: AsyncSession) -> dict[str, float]:
    """% de barrios con amenaza 'Alta' por comuna (0.0-1.0). Comunas sin
    ningún barrio con dato no aparecen en el resultado (no se inventa un 0)."""
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
