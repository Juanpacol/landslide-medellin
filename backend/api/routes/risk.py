import asyncio
from datetime import datetime, timedelta, timezone, date
from typing import Any

from fastapi import APIRouter, Depends
import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LandslideEvent, MLFeature, RiskPrediction
from db.session import get_async_db
from integrations.agent_contracts import predict_all_comunas, predict_risk_stub

router = APIRouter()

_COMUNAS_BASE = [
    ("1", "Popular", True),
    ("2", "Santa Cruz", True),
    ("3", "Manrique", True),
    ("4", "Aranjuez", False),
    ("5", "Castilla", False),
    ("6", "Doce de Octubre", True),
    ("7", "Robledo", True),
    ("8", "Villa Hermosa", True),
    ("9", "Buenos Aires", True),
    ("10", "La Candelaria", False),
    ("11", "Laureles-Estadio", False),
    ("12", "La América", False),
    ("13", "San Javier", True),
    ("14", "El Poblado", False),
    ("15", "Guayabal", False),
    ("16", "Belén", True),
    ("50", "Palmitas", True),
    ("60", "San Cristóbal", True),
    ("70", "Altavista", True),
    ("80", "San Antonio de Prado", True),
    ("90", "Santa Elena", True),
]

_COMUNA_QUERY_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11/query"
)

_POLYGON_CACHE: list[dict[str, Any]] | None = None


def _norm_codigo(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return str(int(s))
    return s


def _arcgis_to_geojson_polygon(geometry: dict[str, Any]) -> dict[str, Any] | None:
    rings = geometry.get("rings")
    if not rings:
        return None
    return {"type": "Polygon", "coordinates": rings}


async def _fetch_single_commune_polygon(client: httpx.AsyncClient, codigo: str) -> dict[str, Any] | None:
    where_codigo = codigo.zfill(2) if codigo not in {"50", "60", "70", "80", "90"} else codigo
    params = {
        "where": f"codigo='{where_codigo}'",
        "outFields": "codigo,nombre,subtipo_comunacorregimiento",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    r = await client.get(_COMUNA_QUERY_URL, params=params)
    r.raise_for_status()
    data = r.json()
    features = data.get("features") or []
    if not features:
        return None
    feat = features[0]
    attrs = feat.get("attributes") or {}
    cid = _norm_codigo(attrs.get("codigo")) or codigo
    name = attrs.get("nombre")
    geo = _arcgis_to_geojson_polygon(feat.get("geometry") or {})
    if not geo:
        return None
    return {"commune_id": cid, "nombre_comuna": name, "geometry": geo}


async def _load_real_commune_polygons() -> list[dict[str, Any]]:
    global _POLYGON_CACHE
    if _POLYGON_CACHE is not None:
        return _POLYGON_CACHE
    async with httpx.AsyncClient(timeout=20.0) as client:
        tasks = [_fetch_single_commune_polygon(client, cid) for cid, _, _ in _COMUNAS_BASE]
        items = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    if out:
        _POLYGON_CACHE = out
    return out


def _risk_to_category(score: float) -> str:
    if score < 0.25:
        return "Bajo"
    if score < 0.50:
        return "Medio"
    if score < 0.75:
        return "Alto"
    return "Crítico"


def _safe_parse_date(value: str | None) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except Exception:
            continue
    return None


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


@router.get("/comunas")
async def get_comunas(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    rows = (await db.execute(select(RiskPrediction).order_by(RiskPrediction.created_at.desc()))).scalars().all()
    pred_by_commune: dict[str, RiskPrediction] = {}
    for r in rows:
        if r.commune_id not in pred_by_commune:
            pred_by_commune[r.commune_id] = r

    real_polygons = await _load_real_commune_polygons()
    geo_by_cid = {g["commune_id"]: g for g in real_polygons if g.get("commune_id")}
    features = []
    for cid, nombre, is_ladera in _COMUNAS_BASE:
        pred = pred_by_commune.get(cid)
        score = float(pred.risk_score) if pred and pred.risk_score is not None else None
        categoria = pred.risk_category if pred and pred.risk_category else "Sin datos"
        n_eventos = 0
        if pred and isinstance(pred.raw_output, dict):
            n_eventos = int(pred.raw_output.get("n_eventos", 0) or 0)
        geo_obj = geo_by_cid.get(cid)
        geom = geo_obj.get("geometry") if geo_obj else None
        display_name = (geo_obj or {}).get("nombre_comuna") or nombre
        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "commune_id": cid,
                "nombre_comuna": display_name,
                "categoria_riesgo": categoria,
                "indice_riesgo": score,
                "n_eventos": n_eventos,
                "is_zona_ladera": is_ladera,
            },
        })

    return {"type": "FeatureCollection", "features": features}


@router.get("/comuna/{commune_id}")
async def get_comuna(commune_id: str, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    pred = (await db.execute(
        select(RiskPrediction)
        .where(RiskPrediction.commune_id == commune_id)
        .order_by(RiskPrediction.created_at.desc())
        .limit(1)
    )).scalars().first()

    base = next((c for c in _COMUNAS_BASE if c[0] == commune_id), None)
    if base is None:
        return {"commune_id": commune_id, "daily_data": []}

    _, nombre, is_ladera = base
    score = float(pred.risk_score) if pred and pred.risk_score is not None else None
    categoria = pred.risk_category if pred and pred.risk_category else "Sin datos"
    n_eventos = 0
    if pred and isinstance(pred.raw_output, dict):
        n_eventos = int(pred.raw_output.get("n_eventos", 0) or 0)

    return {
        "commune_id": commune_id,
        "nombre_comuna": nombre,
        "categoria_riesgo": categoria,
        "indice_riesgo": score,
        "n_eventos": n_eventos,
        "is_zona_ladera": is_ladera,
    }


@router.get("/comuna/{commune_id}/detalle")
async def get_comuna_detalle(commune_id: str, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    base = next((c for c in _COMUNAS_BASE if c[0] == commune_id), None)
    nombre = base[1] if base else commune_id
    is_ladera = base[2] if base else False

    latest_pred_stmt = (
        select(RiskPrediction)
        .where(RiskPrediction.commune_id == commune_id)
        .order_by(RiskPrediction.created_at.desc())
        .limit(1)
    )
    pred = (await db.execute(latest_pred_stmt)).scalars().first()

    today = datetime.now(timezone.utc).date()
    start_30 = today - timedelta(days=29)
    start_7 = today - timedelta(days=6)

    features_stmt = select(MLFeature).where(
        MLFeature.commune_id == commune_id,
        MLFeature.reference_date.isnot(None),
    )
    feature_rows = (await db.execute(features_stmt)).scalars().all()
    rain_by_day: dict[date, float] = {}
    for row in feature_rows:
        if row.reference_date is None:
            continue
        day = row.reference_date.date()
        if day < start_30 or day > today:
            continue
        feature_obj = row.features if isinstance(row.features, dict) else {}
        rain_mm = feature_obj.get("precip_sum_mm_day")
        try:
            rain_by_day[day] = float(rain_mm) if rain_mm is not None else 0.0
        except Exception:
            rain_by_day[day] = 0.0

    rain_7d = round(sum(v for d, v in rain_by_day.items() if d >= start_7), 2)
    rain_30d = round(sum(rain_by_day.values()), 2)
    rain_7d_series = [
        {"date": d.isoformat(), "rainfall": round(rain_by_day.get(d, 0.0), 2)}
        for d in [start_7 + timedelta(days=i) for i in range(7)]
    ]

    events_stmt = (
        select(LandslideEvent)
        .where(LandslideEvent.commune_id == commune_id)
        .order_by(LandslideEvent.ingested_at.desc())
        .limit(20)
    )
    events = (await db.execute(events_stmt)).scalars().all()

    return {
        "commune_id": commune_id,
        "nombre_comuna": nombre,
        "risk_score": float(pred.risk_score) if pred and pred.risk_score is not None else None,
        "risk_category": pred.risk_category if pred and pred.risk_category else "Sin datos",
        "created_at": pred.created_at.isoformat() if pred and pred.created_at else None,
        "rainfall_last_7d_daily": rain_7d_series,
        "rainfall_last_7d_total": rain_7d if rain_by_day else "Sin datos",
        "rainfall_last_30d_total": rain_30d if rain_by_day else "Sin datos",
        "historical_events": [
            {
                "id": e.id,
                "fecha": e.fecha or "Sin datos",
                "tipo_emergencia": e.tipo_emergencia or "Sin datos",
                "barrio": e.barrio or "Sin datos",
            }
            for e in events
        ],
        "is_zona_ladera": is_ladera,
        "model_explanation": pred.explanation if pred and pred.explanation else "Sin datos",
    }


@router.get("/historia/{commune_id}")
async def get_historia(commune_id: str, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=29)

    rain_stmt = select(MLFeature.reference_date, MLFeature.precip_acum_7d).where(
        MLFeature.commune_id == commune_id,
        MLFeature.reference_date.isnot(None),
    )
    rain_rows = (await db.execute(rain_stmt)).all()
    rain_by_day: dict[date, float] = {}
    rain_count_by_day: dict[date, int] = {}
    for row in rain_rows:
        d = row.reference_date.date() if row.reference_date is not None else None
        if d is None:
            continue
        if d < start_day or d > today:
            continue
        rain_by_day[d] = rain_by_day.get(d, 0.0) + float(row.precip_acum_7d or 0.0)
        rain_count_by_day[d] = rain_count_by_day.get(d, 0) + 1

    for d, total in list(rain_by_day.items()):
        count = max(1, rain_count_by_day.get(d, 1))
        rain_by_day[d] = total / count

    events_stmt = select(LandslideEvent.fecha).where(LandslideEvent.commune_id == commune_id)
    event_rows = (await db.execute(events_stmt)).all()
    events_by_day: dict[date, int] = {}
    for row in event_rows:
        d = _safe_parse_date(row.fecha)
        if d is None or d < start_day or d > today:
            continue
        events_by_day[d] = events_by_day.get(d, 0) + 1

    pred_stmt = select(RiskPrediction).where(RiskPrediction.commune_id == commune_id)
    pred_rows = (await db.execute(pred_stmt)).scalars().all()
    pred_by_day: dict[date, dict[str, Any]] = {}
    for p in pred_rows:
        if p.created_at is None:
            continue
        d = p.created_at.date()
        if d < start_day or d > today:
            continue
        current = pred_by_day.get(d)
        if current is None or (current.get("created_at") or datetime.min.replace(tzinfo=timezone.utc)) < p.created_at:
            pred_by_day[d] = {
                "risk_score": float(p.risk_score) if p.risk_score is not None else None,
                "risk_category": p.risk_category or "Sin datos",
                "created_at": p.created_at,
            }

    daily_data: list[dict[str, Any]] = []
    for i in range(30):
        d = start_day + timedelta(days=i)
        pred_info = pred_by_day.get(d, {})
        daily_data.append(
            {
                "date": d.isoformat(),
                "rainfall": round(rain_by_day.get(d, 0.0), 2),
                "landslides": int(events_by_day.get(d, 0)),
                "risk_score": pred_info.get("risk_score"),
                "risk_category": pred_info.get("risk_category", "Sin datos"),
            }
        )

    return {"commune_id": commune_id, "daily_data": daily_data}


@router.get("/estadisticas")
async def get_estadisticas(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    total_comunas = len(_COMUNAS_BASE)

    latest_pred_sq = (
        select(RiskPrediction.commune_id, func.max(RiskPrediction.created_at).label("latest_created_at"))
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )
    latest_preds_stmt = select(RiskPrediction).join(
        latest_pred_sq,
        (RiskPrediction.commune_id == latest_pred_sq.c.commune_id)
        & (RiskPrediction.created_at == latest_pred_sq.c.latest_created_at),
    )
    latest_preds = (await db.execute(latest_preds_stmt)).scalars().all()
    risk_critico = sum(1 for p in latest_preds if (p.risk_category or "").strip().lower() in {"crítico", "critico"})
    risk_alto = sum(1 for p in latest_preds if (p.risk_category or "").strip().lower() == "alto")

    today = datetime.now(timezone.utc).date()
    start_30 = today - timedelta(days=30)
    start_14 = today - timedelta(days=14)
    start_7 = today - timedelta(days=7)

    events_30 = (await db.execute(select(LandslideEvent))).scalars().all()
    total_events_30d = 0
    for e in events_30:
        d = _safe_parse_date(e.fecha)
        if d and d >= start_30:
            total_events_30d += 1

    recent_preds = (await db.execute(select(RiskPrediction).where(RiskPrediction.created_at >= start_14))).scalars().all()
    prev_scores: list[float] = []
    curr_scores: list[float] = []
    for p in recent_preds:
        if p.created_at is None or p.risk_score is None:
            continue
        if p.created_at.date() >= start_7:
            curr_scores.append(float(p.risk_score))
        else:
            prev_scores.append(float(p.risk_score))
    prev_avg = (sum(prev_scores) / len(prev_scores)) if prev_scores else None
    curr_avg = (sum(curr_scores) / len(curr_scores)) if curr_scores else None
    trend = "Sin datos"
    if prev_avg is not None and curr_avg is not None:
        trend = "subió" if curr_avg > prev_avg else "bajó"

    return {
        "total_comunas_monitoreadas": total_comunas,
        "comunas_riesgo_critico": risk_critico,
        "comunas_riesgo_alto": risk_alto,
        "total_eventos_ultimos_30_dias": total_events_30d,
        "tendencia_riesgo_semana": trend,
    }


@router.get("/alerts")
async def get_alerts(db: AsyncSession = Depends(get_async_db)) -> list[dict[str, Any]]:
    rows = (await db.execute(select(RiskPrediction))).scalars().all()
    alerts: list[dict[str, Any]] = []
    by_cid = {cid: name for cid, name, _ in _COMUNAS_BASE}
    for r in rows:
        if r.risk_category not in {"Alto", "Crítico"}:
            continue
        alerts.append({
            "id": r.id,
            "commune_id": r.commune_id,
            "nombre_comuna": by_cid.get(r.commune_id, r.commune_id),
            "nivel": "Rojo" if r.risk_category == "Crítico" else "Naranja",
            "precipitacion_7d": 0,
            "n_eventos_recientes": None,
            "fecha_alerta": r.created_at.isoformat() if r.created_at else None,
        })
    alerts.sort(key=lambda a: 0 if a["nivel"] == "Rojo" else 1)
    return alerts[:10]


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
