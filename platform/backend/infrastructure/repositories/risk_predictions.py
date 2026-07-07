"""
Repositorio de RiskPrediction — encapsula la query "última predicción por
comuna", que antes vivía copiada en alerts/slack.py (×2, lluvia y crítico),
api/routes/rain.py (/live) y api/routes/risk.py (/comunas, con variante de
cutoff). Un solo lugar para el patrón subquery-max-join.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.risk_prediction import RiskPrediction


async def latest_by_commune(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, RiskPrediction]:
    """Última RiskPrediction por comuna. `since` acota la búsqueda (p.ej.
    7 días en /comunas: las predicciones corren cada 6h, no hace falta leer
    la tabla completa)."""
    subq = select(
        RiskPrediction.commune_id,
        func.max(RiskPrediction.created_at).label("max_at"),
    )
    if since is not None:
        subq = subq.where(RiskPrediction.created_at >= since)
    subq = subq.group_by(RiskPrediction.commune_id).subquery()

    result = await session.execute(
        select(RiskPrediction).join(
            subq,
            (RiskPrediction.commune_id == subq.c.commune_id)
            & (RiskPrediction.created_at == subq.c.max_at),
        )
    )
    return {r.commune_id: r for r in result.scalars().all()}


async def latest_scores_by_commune(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, tuple[float | None, str | None]]:
    """Variante liviana: commune_id → (risk_score, risk_category)."""
    rows = await latest_by_commune(session, since=since)
    return {cid: (r.risk_score, r.risk_category) for cid, r in rows.items()}
