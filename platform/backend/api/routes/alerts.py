"""
Endpoints de alertas: sirve las gráficas PNG que acompañan las alertas,
permite disparar una alerta de prueba enriquecida y genera el reporte de
situación en lenguaje plano (con envío opcional a Slack).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tools import commune_display_name
from alerts.charts import rainfall_chart_for_commune
from api.auth import require_token
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


@router.get("/evacuation-routes/{commune_id}")
async def get_evacuation_routes_endpoint(
    commune_id: str,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Zonas seguras candidatas (parques/colegios/estadios de OpenStreetMap)
    más cercanas a una comuna, con ruta caminando. MVP sin validar por
    Defensoría/DAGRD — ver `alerts/evacuation.py`."""
    from alerts.evacuation import get_evacuation_routes

    return await get_evacuation_routes(db, commune_id)


@router.post("/report", dependencies=[Depends(require_token)])
async def create_situation_report(
    send_to_slack: bool = Query(False, description="Además de devolverlo, publicarlo en Slack"),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Genera el reporte de situación del valle en lenguaje plano (≤200 palabras)."""
    from alerts.reports import generate_situation_report, send_situation_report_to_slack

    report = await generate_situation_report(db)
    slack_sent = False
    if send_to_slack:
        slack_sent = await send_situation_report_to_slack(db)
    return {"report": report, "slack_sent": slack_sent}
