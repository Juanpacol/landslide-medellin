"""
Alert endpoints: serves the PNG charts that accompany alerts, lets you
fire an enriched test alert, and generates the plain-language situation
report (with optional Slack delivery).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
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
    """Returns the rain PNG chart (with threshold and peak) for a commune."""
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
    """Candidate safe zones (OpenStreetMap parks/schools/stadiums) nearest
    to a commune, with a walking route. MVP not validated by
    Defensoría/DAGRD — see `alerts/evacuation.py`."""
    from alerts.evacuation import get_evacuation_routes

    return await get_evacuation_routes(db, commune_id)


@router.post("/report", dependencies=[Depends(require_token)])
async def create_situation_report(
    request: Request,
    send_to_slack: bool = Query(False, description="In addition to returning it, post it to Slack"),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Generates the valley's plain-language situation report (≤200 words)."""
    from api.audit import log_audit_event
    from alerts.reports import generate_situation_report, send_situation_report_to_slack

    log_audit_event(
        session=db,
        request=request,
        action="situation_report",
        resource="valley",
        summary=f"Reporte de situación generado (slack={send_to_slack})",
    )
    report = await generate_situation_report(db)
    slack_sent = False
    if send_to_slack:
        slack_sent = await send_situation_report_to_slack(db)
    await db.commit()
    return {"report": report, "slack_sent": slack_sent}
