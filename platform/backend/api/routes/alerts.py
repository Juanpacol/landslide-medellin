"""
Endpoints de alertas: sirve las gráficas PNG que acompañan las alertas y
permite disparar una alerta de prueba enriquecida.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tools import commune_display_name
from alerts.charts import rainfall_chart_for_commune
from db.models.commune_threshold import CommuneThreshold
from db.models.risk_prediction import RiskPrediction
from db.session import get_async_db

router = APIRouter()


async def _threshold_for(commune_id: str, db: AsyncSession) -> float:
    row = await db.get(CommuneThreshold, commune_id)
    return float(row.threshold_mm) if row and row.threshold_mm else 35.0


async def _latest_risk(commune_id: str, db: AsyncSession) -> tuple[str | None, float | None]:
    stmt = (
        select(RiskPrediction.risk_category, RiskPrediction.risk_score)
        .where(RiskPrediction.commune_id == commune_id)
        .order_by(RiskPrediction.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None, None
    return row[0], (float(row[1]) if row[1] is not None else None)


@router.get("/chart/{commune_id}")
async def get_alert_chart(
    commune_id: str,
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Devuelve la gráfica PNG de lluvia (con umbral y pico) para una comuna."""
    threshold = await _threshold_for(commune_id, db)
    category, score = await _latest_risk(commune_id, db)
    name = commune_display_name(commune_id)
    png, _ = await rainfall_chart_for_commune(
        commune_id, db, threshold, name, category, score, days=days
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
