from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RiskPrediction
from db.session import get_async_db
from integrations.agent_contracts import predict_all_comunas, predict_risk_stub

router = APIRouter()


class PredictCommuneBody(BaseModel):
    commune_id: str = Field(..., min_length=1, max_length=64)


@router.get("/predictions/latest")
async def latest_predictions(
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    stmt = (
        select(RiskPrediction)
        .order_by(RiskPrediction.created_at.desc())
        .limit(min(limit, 200))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "commune_id": r.commune_id,
                "risk_score": r.risk_score,
                "risk_category": r.risk_category,
                "model_version": r.model_version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/predict-all")
async def run_predict_all(db: AsyncSession = Depends(get_async_db)) -> dict[str, str]:
    await predict_all_comunas(db)
    return {"status": "accepted"}


@router.post("/predict-commune")
async def run_predict_commune(
    body: PredictCommuneBody,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    return await predict_risk_stub(body.commune_id, db)
