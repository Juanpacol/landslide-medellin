from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from scipy.stats import spearmanr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.alert_log import AlertLog
from db.models.app_setting import AppSetting
from db.models.commune_threshold import CommuneThreshold
from db.models.landslide_event import LandslideEvent
from db.models.ml_feature import MLFeature
from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.risk_prediction import RiskPrediction
from db.session import get_async_db

logger = logging.getLogger(__name__)
router = APIRouter()

COL_TZ = ZoneInfo("America/Bogota")

_COMUNAS: list[tuple[str, str]] = [
    ("1", "Popular"), ("2", "Santa Cruz"), ("3", "Manrique"), ("4", "Aranjuez"),
    ("5", "Castilla"), ("6", "Doce de Octubre"), ("7", "Robledo"), ("8", "Villa Hermosa"),
    ("9", "Buenos Aires"), ("10", "La Candelaria"), ("11", "Laureles-Estadio"),
    ("12", "La América"), ("13", "San Javier"), ("14", "El Poblado"), ("15", "Guayabal"),
    ("16", "Belén"), ("50", "Palmitas"), ("60", "San Cristóbal"), ("70", "Altavista"),
    ("80", "San Antonio de Prado"), ("90", "Santa Elena"),
]
_NAMES: dict[str, str] = dict(_COMUNAS)


def _midnight_utc() -> datetime:
    now_col = datetime.now(COL_TZ)
    return now_col.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


# ── Live rainfall ──────────────────────────────────────────────────────────────

@router.get("/live")
async def get_live_rainfall(session: AsyncSession = Depends(get_async_db)) -> dict:
    midnight = _midnight_utc()

    rows = await session.execute(
        select(
            RainfallTimeseries.commune_id,
            RainfallTimeseries.snapshot_at,
            RainfallTimeseries.precip_mm,
        )
        .where(RainfallTimeseries.snapshot_at >= midnight)
        .order_by(RainfallTimeseries.commune_id, RainfallTimeseries.snapshot_at)
    )

    by_commune: dict[str, list[dict]] = defaultdict(list)
    running: dict[str, float] = {}
    for cid, snap_at, pmm in rows.all():
        running[cid] = running.get(cid, 0.0) + pmm
        by_commune[cid].append({
            "time": snap_at.astimezone(COL_TZ).strftime("%H:%M"),
            "snapshot_mm": round(pmm, 2),
            "acum_mm": round(running[cid], 2),
        })

    threshold_rows = await session.execute(select(CommuneThreshold))
    thresholds: dict[str, float] = {r.commune_id: r.threshold_mm for r in threshold_rows.scalars().all()}

    subq = (
        select(RiskPrediction.commune_id, func.max(RiskPrediction.created_at).label("max_at"))
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )
    risk_rows = await session.execute(
        select(RiskPrediction).join(
            subq,
            (RiskPrediction.commune_id == subq.c.commune_id)
            & (RiskPrediction.created_at == subq.c.max_at),
        )
    )
    risks: dict[str, tuple[float, str]] = {
        r.commune_id: (r.risk_score, r.risk_category) for r in risk_rows.scalars().all()
    }

    now_utc = datetime.now(timezone.utc)
    comunas_out = []
    for cid, name in _COMUNAS:
        acum = round(running.get(cid, 0.0), 2)
        threshold = thresholds.get(cid, 35.0)
        risk_score, risk_category = risks.get(cid, (None, None))
        comunas_out.append({
            "commune_id": cid,
            "nombre_comuna": name,
            "snapshots": by_commune.get(cid, []),
            "precip_acum_mm": acum,
            "threshold_mm": threshold,
            "is_over_threshold": acum > threshold,
            "risk_score": risk_score,
            "risk_category": risk_category,
        })

    return {
        "date": now_utc.astimezone(COL_TZ).strftime("%Y-%m-%d"),
        "updated_at": now_utc.isoformat(),
        "comunas": comunas_out,
    }


# ── Spearman correlation ───────────────────────────────────────────────────────

@router.get("/spearman")
async def get_spearman(session: AsyncSession = Depends(get_async_db)) -> dict:
    # Daily average rainfall per commune from SIATA snapshots
    rain_rows = await session.execute(
        select(MLFeature.commune_id, MLFeature.reference_date, MLFeature.features)
        .where(MLFeature.features["source"].astext == "siata")
        .where(MLFeature.reference_date.isnot(None))
        .order_by(MLFeature.reference_date)
    )

    daily_rain: dict[tuple[str, str], list[float]] = defaultdict(list)
    for cid, ref_date, features in rain_rows.all():
        if not features:
            continue
        precip = features.get("mean_precip_mm_snapshot")
        if precip is None:
            continue
        day_str = ref_date.astimezone(COL_TZ).strftime("%Y-%m-%d")
        daily_rain[(cid, day_str)].append(float(precip))

    rain_by_day: dict[tuple[str, str], float] = {
        k: sum(v) / len(v) for k, v in daily_rain.items()
    }

    # Daily event count per commune
    event_rows = await session.execute(
        select(LandslideEvent.commune_id, LandslideEvent.fecha)
        .where(LandslideEvent.commune_id.isnot(None))
        .where(LandslideEvent.fecha.isnot(None))
    )
    events_by_day: dict[tuple[str, str], int] = defaultdict(int)
    for cid, fecha_str in event_rows.all():
        if not fecha_str or not cid:
            continue
        day_str = str(fecha_str)[:10]
        events_by_day[(cid, day_str)] += 1

    comunas_out = []
    for cid, name in _COMUNAS:
        days_with_rain: dict[str, float] = {}
        for (c, day), rain in rain_by_day.items():
            if c == cid:
                days_with_rain[day] = rain

        scatter = [
            {
                "rainfall_mm": round(rain, 2),
                "n_events": events_by_day.get((cid, day), 0),
                "date": day,
            }
            for day, rain in sorted(days_with_rain.items())
        ]

        rho = p_value = None
        if len(scatter) >= 5:
            xs = [s["rainfall_mm"] for s in scatter]
            ys = [s["n_events"] for s in scatter]
            try:
                res = spearmanr(xs, ys)
                rho = round(float(res.statistic), 3)
                p_value = round(float(res.pvalue), 4)
            except Exception:
                pass

        comunas_out.append({
            "commune_id": cid,
            "nombre_comuna": name,
            "rho": rho,
            "p_value": p_value,
            "n_observations": len(scatter),
            "scatter_data": scatter[-120:],
        })

    return {"comunas": comunas_out}


# ── Thresholds ─────────────────────────────────────────────────────────────────

class ThresholdIn(BaseModel):
    threshold_mm: float


@router.get("/thresholds")
async def get_thresholds(session: AsyncSession = Depends(get_async_db)) -> dict:
    rows = await session.execute(select(CommuneThreshold))
    saved: dict[str, float] = {r.commune_id: r.threshold_mm for r in rows.scalars().all()}
    return {
        "thresholds": [
            {"commune_id": cid, "nombre_comuna": name, "threshold_mm": saved.get(cid, 35.0)}
            for cid, name in _COMUNAS
        ]
    }


@router.put("/thresholds/{commune_id}")
async def set_threshold(
    commune_id: str,
    body: ThresholdIn,
    session: AsyncSession = Depends(get_async_db),
) -> dict:
    existing = await session.get(CommuneThreshold, commune_id)
    if existing:
        existing.threshold_mm = body.threshold_mm
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(CommuneThreshold(commune_id=commune_id, threshold_mm=body.threshold_mm))
    await session.commit()
    return {"commune_id": commune_id, "threshold_mm": body.threshold_mm}


# ── Webhook settings ───────────────────────────────────────────────────────────

class WebhookIn(BaseModel):
    url: str


@router.get("/settings/webhook")
async def get_webhook(session: AsyncSession = Depends(get_async_db)) -> dict:
    row = await session.get(AppSetting, "slack_webhook_url")
    if not row or not row.value:
        return {"configured": False, "masked_url": None}
    url = row.value
    masked = url[:30] + "…" + url[-8:] if len(url) > 40 else url
    return {"configured": True, "masked_url": masked}


@router.post("/settings/webhook")
async def save_webhook(body: WebhookIn, session: AsyncSession = Depends(get_async_db)) -> dict:
    existing = await session.get(AppSetting, "slack_webhook_url")
    if existing:
        existing.value = body.url
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(AppSetting(key="slack_webhook_url", value=body.url))
    await session.commit()
    return {"ok": True}


@router.post("/settings/webhook/test")
async def test_webhook(session: AsyncSession = Depends(get_async_db)) -> dict:
    from alerts.slack import _build_slack_payload, _fire_slack

    row = await session.get(AppSetting, "slack_webhook_url")
    if not row or not row.value:
        return {"ok": False, "error": "No hay webhook URL configurada"}
    payload = _build_slack_payload("0", "Prueba TEYVA", 42.0, 35.0, 0.85, "Alto")
    payload["blocks"].insert(0, {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "✅ *Este es un mensaje de prueba del sistema TEYVA*"},
    })
    status, code = await _fire_slack(row.value, payload)
    return {"ok": status == "sent", "status": status, "response_code": code}


# ── Alert log ──────────────────────────────────────────────────────────────────

@router.get("/alerts/log")
async def get_alert_log(session: AsyncSession = Depends(get_async_db)) -> dict:
    rows = await session.execute(
        select(AlertLog).order_by(AlertLog.created_at.desc()).limit(50)
    )
    return {
        "logs": [
            {
                "id": r.id,
                "commune_id": r.commune_id,
                "nombre_comuna": _NAMES.get(r.commune_id, r.commune_id),
                "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
                "precip_acum_mm": r.precip_acum_mm,
                "threshold_mm": r.threshold_mm,
                "risk_score": r.risk_score,
                "risk_category": r.risk_category,
                "status": r.status,
            }
            for r in rows.scalars().all()
        ]
    }
