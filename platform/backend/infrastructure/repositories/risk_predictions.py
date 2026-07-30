"""
RiskPrediction repository — encapsulates the "latest prediction per
commune" query, previously copied across alerts/slack.py (×2, rain and
critical), api/routes/rain.py (/live) and api/routes/risk.py (/comunas,
with a cutoff variant). One single place for the subquery-max-join pattern.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.risk_prediction import RiskPrediction


async def latest_by_commune(
    session: AsyncSession, *, since: datetime | None = None
) -> dict[str, RiskPrediction]:
    """Latest RiskPrediction per commune. `since` bounds the search (e.g.
    7 days in /comunas: predictions run every 6h, no need to read the whole
    table)."""
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
    """Lightweight variant: commune_id → (risk_score, risk_category)."""
    rows = await latest_by_commune(session, since=since)
    return {cid: (r.risk_score, r.risk_category) for cid, r in rows.items()}
