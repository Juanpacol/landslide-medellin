import asyncio
import json
import logging
from datetime import datetime, time, timedelta, timezone, date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
import httpx

from api.auth import require_token
from api.rate_limit import rate_limit
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from domain.risk_rules import (
    alert_level,
    compute_alert_state,
    is_alert_category,
    normalize_category,
)
from db.models import LandslideEvent, MLFeature, RiskPrediction
from db.models.rainfall_timeseries import RainfallTimeseries
from db.models.risk_explanation import RiskExplanation
from db.session import get_async_db

# Territorio desde la fuente única (domain/communes.py), en id CANÓNICO —
# el mismo que usan risk_predictions/ml_features. El código oficial (ArcGIS)
# solo se usa al pedir polígonos (_load_real_commune_polygons).
from domain.communes import BY_ID as _COMMUNES_BY_ID
from domain.communes import COMMUNES as _DOMAIN_COMMUNES
from domain.communes import canonical_id as _canonical_commune_id
from integrations.agent_contracts import predict_all_comunas, predict_risk_stub

router = APIRouter()

_COMUNAS_BASE = [(c.id, c.nombre, c.is_ladera) for c in _DOMAIN_COMMUNES]

_COMUNA_QUERY_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11/query"
)

_POLYGON_CACHE: list[dict[str, Any]] | None = None
# Cache en disco: los polígonos de comunas son datos de referencia estáticos.
# Persistirlos evita reconstruir el cache con 21 llamadas HTTP a ArcGIS en cada
# arranque del proceso (cold start de ~1-3s).
_POLYGON_CACHE_FILE = Path(__file__).resolve().parent / "_commune_polygons_cache.json"


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


async def _fetch_single_commune_polygon(
    client: httpx.AsyncClient, codigo: str
) -> dict[str, Any] | None:
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
    # 1) Cache en memoria (proceso vivo).
    if _POLYGON_CACHE is not None:
        return _POLYGON_CACHE

    # 2) Cache en disco (sobrevive reinicios; polígonos son estáticos).
    if _POLYGON_CACHE_FILE.exists():
        try:
            cached = json.loads(_POLYGON_CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached:
                for item in cached:
                    if isinstance(item, dict):
                        item["commune_id"] = _canonical_commune_id(item.get("commune_id"))
                _POLYGON_CACHE = cached
                return _POLYGON_CACHE
        except Exception:
            logging.getLogger(__name__).warning(
                "Cache de polígonos en disco corrupto; se regenerará desde ArcGIS."
            )

    # 3) Fetch desde ArcGIS (por código OFICIAL) y persiste a disco.
    async with httpx.AsyncClient(timeout=20.0) as client:
        tasks = [
            _fetch_single_commune_polygon(client, _COMMUNES_BY_ID[cid].official_code)
            for cid, _, _ in _COMUNAS_BASE
        ]
        items = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            # ArcGIS responde con el código oficial → traducir al id canónico
            # para que el frontend y las predicciones hablen el mismo idioma.
            item["commune_id"] = _canonical_commune_id(item.get("commune_id"))
            out.append(item)
    if out:
        _POLYGON_CACHE = out
        try:
            _POLYGON_CACHE_FILE.write_text(json.dumps(out), encoding="utf-8")
        except Exception:
            logging.getLogger(__name__).warning(
                "No se pudo escribir el cache de polígonos a disco."
            )
    return out


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
    stmt = select(RiskPrediction).order_by(RiskPrediction.created_at.desc()).limit(min(limit, 200))
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
    # Acota a predicciones recientes (las predicciones corren cada 6h, 7 días
    # cubre de sobra) en vez de traer toda la tabla y quedarnos con la última.
    from infrastructure.repositories.risk_predictions import latest_by_commune

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    pred_by_commune: dict[str, RiskPrediction] = await latest_by_commune(db, since=cutoff)

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
        features.append(
            {
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
            }
        )

    return {"type": "FeatureCollection", "features": features}


@router.get("/comuna/{commune_id}")
async def get_comuna(commune_id: str, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    pred = (
        (
            await db.execute(
                select(RiskPrediction)
                .where(RiskPrediction.commune_id == commune_id)
                .order_by(RiskPrediction.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

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


async def _rain_by_day_for_commune(
    db: AsyncSession, commune_id: str, start_day: date, end_day: date
) -> dict[date, float]:
    """Lluvia diaria real de una comuna: suma de snapshots SIATA agrupados por
    día (`rainfall_timeseries`, la tabla que SIATA sí llena cada 30 min — mismo
    patrón que `alerts/slack.py::_get_today_acum`). Los días sin telemetría se
    rellenan con el total diario de IDEAM (`features.precip_sum_mm_day`) si
    existe. NO leer `MLFeature.precip_acum_7d`: ningún scraper la llena."""
    start_dt = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
    stmt = (
        select(
            func.date(RainfallTimeseries.snapshot_at),
            func.sum(RainfallTimeseries.precip_mm),
        )
        .where(
            RainfallTimeseries.commune_id == commune_id,
            RainfallTimeseries.snapshot_at >= start_dt,
        )
        .group_by(func.date(RainfallTimeseries.snapshot_at))
    )
    rain_by_day: dict[date, float] = {}
    for day_value, total in (await db.execute(stmt)).all():
        d = (
            day_value
            if isinstance(day_value, date)
            else datetime.fromisoformat(str(day_value)).date()
        )
        if start_day <= d <= end_day:
            rain_by_day[d] = round(float(total or 0.0), 2)

    feats_stmt = select(MLFeature.reference_date, MLFeature.features).where(
        MLFeature.commune_id == commune_id,
        MLFeature.reference_date.isnot(None),
    )
    for ref, feats in (await db.execute(feats_stmt)).all():
        d = ref.date()
        if d < start_day or d > end_day or d in rain_by_day:
            continue
        value = feats.get("precip_sum_mm_day") if isinstance(feats, dict) else None
        try:
            if value is not None:
                rain_by_day[d] = round(float(value), 2)
        except (TypeError, ValueError):
            continue
    return rain_by_day


@router.get("/comuna/{commune_id}/detalle")
async def get_comuna_detalle(
    commune_id: str, db: AsyncSession = Depends(get_async_db)
) -> dict[str, Any]:
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

    rain_by_day = await _rain_by_day_for_commune(db, commune_id, start_30, today)

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
        "predicted_at": pred.created_at.isoformat() if pred and pred.created_at else None,
    }


@router.get("/barrios-hazard")
async def get_barrios_hazard(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Grado de amenaza geomorfológica oficial por barrio (~401 polígonos).

    Poblada por `scraper/barrio_hazard.py` (script puntual — la cartografía de
    ordenamiento territorial cambia en meses/años). El frontend la une con
    `barrios-medellin.json` por `codigo` para colorear la capa de barrios.
    """
    from db.models.barrio_hazard import BarrioHazard

    rows = (await db.execute(select(BarrioHazard))).scalars().all()
    return {
        "barrios": {
            r.barrio_codigo: {
                "nombre": r.nombre,
                "commune_id": r.commune_id,
                "hazard_grade": r.hazard_grade,
            }
            for r in rows
        },
        "total": len(rows),
    }


@router.get("/seismic-events")
async def get_seismic_events(
    days: int = 365,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Sismos recientes registrados por la red SIATA (sismógrafos/acelerógrafos).

    Un mismo sismo lo registran varias estaciones; se deduplica por
    (fecha_evento, epicentro) devolviendo un registro por sismo con las
    estaciones que lo captaron.
    """
    from db.models.seismic_event import SeismicEvent

    days = max(1, min(int(days), 3650))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(SeismicEvent)
        .where((SeismicEvent.event_local_at >= cutoff) | (SeismicEvent.event_local_at.is_(None)))
        .order_by(SeismicEvent.event_local_at.desc().nulls_last())
        .limit(200)
    )
    rows = (await db.execute(stmt)).scalars().all()

    dedup: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (
            r.event_local_at.isoformat() if r.event_local_at else None,
            r.epicenter_label,
        )
        if key not in dedup:
            dedup[key] = {
                "event_local_at": r.event_local_at.isoformat() if r.event_local_at else None,
                "magnitude": r.magnitude,
                "depth_km": r.depth_km,
                "epicenter_lat": r.epicenter_lat,
                "epicenter_lon": r.epicenter_lon,
                "epicenter_label": r.epicenter_label,
                "stations": [],
            }
        if r.station_name not in dedup[key]["stations"]:
            dedup[key]["stations"].append(r.station_name)

    events = sorted(
        dedup.values(),
        key=lambda e: e["event_local_at"] or "",
        reverse=True,
    )
    return {"events": events, "total": len(events)}


async def _inherited_risk_for_communes(db: AsyncSession, commune_ids: list[str]) -> dict[str, Any]:
    """Peor riesgo entre las comunas que intersecta una cuadrícula. No es una
    predicción por cuadrícula — se hereda del modelo a nivel comuna."""
    worst_score: float | None = None
    worst_category: str | None = None
    for cid in commune_ids:
        pred = (
            (
                await db.execute(
                    select(RiskPrediction)
                    .where(RiskPrediction.commune_id == cid)
                    .order_by(RiskPrediction.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if pred and pred.risk_score is not None:
            if worst_score is None or pred.risk_score > worst_score:
                worst_score = float(pred.risk_score)
                worst_category = pred.risk_category
    return {
        "risk_score": worst_score,
        "risk_category": worst_category or "Sin datos",
        "risk_source": "inherited_from_commune",
    }


@router.get("/mesh-grid")
async def get_mesh_grid(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Cuadrículas de ~1.5km (metodología JMA Mesh Maps). Generadas por
    `scraper/mesh_grid.py`. El riesgo se hereda de la comuna (ver
    `MeshQuadrant.__doc__`) — no es predicción por cuadrícula."""
    from db.models.mesh_quadrant import MeshQuadrant

    rows = (await db.execute(select(MeshQuadrant))).scalars().all()
    return {
        "quadrants": [
            {
                "id": r.id,
                "geometry": r.geometry,
                "commune_ids": r.commune_ids,
                "barrio_codigos": r.barrio_codigos,
                "hazard_grade": r.hazard_grade,
                "n_barrios_alta": r.n_barrios_alta,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/mesh-grid/{quad_id}")
async def get_mesh_quadrant_detail(
    quad_id: str, db: AsyncSession = Depends(get_async_db)
) -> dict[str, Any]:
    from db.models.mesh_quadrant import MeshQuadrant

    row = await db.get(MeshQuadrant, quad_id)
    if row is None:
        return {"error": "Cuadrícula no encontrada"}

    inherited = await _inherited_risk_for_communes(db, row.commune_ids)
    return {
        "id": row.id,
        "geometry": row.geometry,
        "commune_ids": row.commune_ids,
        "barrio_codigos": row.barrio_codigos,
        "hazard_grade": row.hazard_grade,
        "n_barrios_alta": row.n_barrios_alta,
        **inherited,
    }


@router.get("/snake-line/{commune_id}")
async def get_snake_line(
    commune_id: str, db: AsyncSession = Depends(get_async_db)
) -> dict[str, Any]:
    """Punto actual + historial 48h del gráfico Snake Line (SWI × lluvia
    intensa), metodología JMA. Ver `alerts/snake_line.py`."""
    from alerts.snake_line import get_snake_line_status

    return await get_snake_line_status(db, commune_id)


@router.get("/soil-water-index")
async def get_soil_water_index(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Saturación estimada del suelo (%) por comuna — metodología JMA (tanque
    simplificado). Ver `ml/soil_water_index.py` para el detalle del modelo y
    sus límites (MVP, drain_rate conservador sin calibrar)."""
    from ml.soil_water_index import swi_for_all_communes

    today = datetime.now(timezone.utc).date()
    swi_by_commune = await swi_for_all_communes(db, today)

    items = []
    for cid, nombre, _ in _COMUNAS_BASE:
        swi = swi_by_commune.get(cid)
        items.append(
            {
                "commune_id": cid,
                "nombre_comuna": nombre,
                "swi_pct": swi,
                "state": "ROJO"
                if swi is not None and swi >= 85
                else "AMARILLO"
                if swi is not None and swi >= 60
                else "VERDE",
            }
        )
    return {"items": items, "total": len(items), "as_of": today.isoformat()}


async def _alert_state_for_commune(
    db: AsyncSession,
    commune_id: str,
    threshold_mm: float,
    rain_today_mm: float,
    antecedent_index: float,
) -> dict[str, Any]:
    pred = (
        (
            await db.execute(
                select(RiskPrediction)
                .where(RiskPrediction.commune_id == commune_id)
                .order_by(RiskPrediction.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    risk_category = pred.risk_category if pred else None

    from domain.risk_rules import ANTECEDENT_INDEX_THRESHOLD_MM

    rainfall_pct = round(rain_today_mm / threshold_mm, 3) if threshold_mm else 0.0
    antecedent_pct = round(antecedent_index / ANTECEDENT_INDEX_THRESHOLD_MM, 3)
    result = compute_alert_state(rainfall_pct, antecedent_pct, risk_category)

    return {
        "commune_id": commune_id,
        "state": result["state"],
        "action": result["action"],
        "rainfall_today_mm": round(rain_today_mm, 1),
        "rainfall_threshold_mm": threshold_mm,
        "rainfall_pct": rainfall_pct,
        "antecedent_index": antecedent_index,
        "antecedent_pct": antecedent_pct,
        "risk_category": risk_category or "Sin datos",
        "risk_score": float(pred.risk_score) if pred and pred.risk_score is not None else None,
    }


@router.get("/alert-state/{commune_id}")
async def get_alert_state(
    commune_id: str, db: AsyncSession = Depends(get_async_db)
) -> dict[str, Any]:
    """Estado operativo compuesto (Verde/Amarillo/Rojo) para una comuna: cruza
    lluvia de hoy, índice de precipitación antecedente y categoría del modelo
    ML. Reutiliza el mismo umbral por comuna que las alertas de Slack."""
    from db.models.commune_threshold import CommuneThreshold
    from ml.precip_index import antecedent_indexes_for_all_communes

    today = datetime.now(timezone.utc).date()
    threshold_row = await db.get(CommuneThreshold, commune_id)
    threshold_mm = threshold_row.threshold_mm if threshold_row else 35.0

    rain_by_day = await _rain_by_day_for_commune(db, commune_id, today, today)
    rain_today = rain_by_day.get(today, 0.0)

    antecedent_by_commune = await antecedent_indexes_for_all_communes(db, today)
    antecedent_index = antecedent_by_commune.get(commune_id, 0.0)

    return await _alert_state_for_commune(
        db, commune_id, threshold_mm, rain_today, antecedent_index
    )


@router.get("/alert-state")
async def get_alert_state_all(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Estado compuesto de las 21 comunas, para el dashboard."""
    from db.models.commune_threshold import CommuneThreshold
    from ml.precip_index import antecedent_indexes_for_all_communes

    today = datetime.now(timezone.utc).date()
    thresholds = {
        r.commune_id: r.threshold_mm
        for r in (await db.execute(select(CommuneThreshold))).scalars().all()
    }
    antecedent_by_commune = await antecedent_indexes_for_all_communes(db, today)

    items = []
    for cid, _, _ in _COMUNAS_BASE:
        threshold_mm = thresholds.get(cid, 35.0)
        rain_by_day = await _rain_by_day_for_commune(db, cid, today, today)
        rain_today = rain_by_day.get(today, 0.0)
        antecedent_index = antecedent_by_commune.get(cid, 0.0)
        items.append(
            await _alert_state_for_commune(db, cid, threshold_mm, rain_today, antecedent_index)
        )

    items.sort(key=lambda it: {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}[it["state"]])
    return {"items": items, "total": len(items)}


@router.get("/explanation/{commune_id}")
async def get_risk_explanation(
    commune_id: str,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    """Explicación narrativa más reciente generada por el servicio de IA."""
    stmt = (
        select(RiskExplanation)
        .where(RiskExplanation.commune_id == commune_id)
        .order_by(RiskExplanation.generated_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return {
            "commune_id": commune_id,
            "explanation": None,
            "explanation_json": None,
            "generated_by": None,
            "generated_at": None,
        }
    return {
        "commune_id": row.commune_id,
        "risk_score": row.risk_score,
        "risk_category": row.risk_category,
        "explanation": row.explanation,
        "explanation_json": row.explanation_json,
        "generated_by": row.generated_by,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
    }


@router.get("/historia/{commune_id}")
async def get_historia(commune_id: str, db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start_day = today - timedelta(days=29)

    rain_by_day = await _rain_by_day_for_commune(db, commune_id, start_day, today)

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
        if (
            current is None
            or (current.get("created_at") or datetime.min.replace(tzinfo=timezone.utc))
            < p.created_at
        ):
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
        select(
            RiskPrediction.commune_id,
            func.max(RiskPrediction.created_at).label("latest_created_at"),
        )
        .group_by(RiskPrediction.commune_id)
        .subquery()
    )
    latest_preds_stmt = select(RiskPrediction).join(
        latest_pred_sq,
        (RiskPrediction.commune_id == latest_pred_sq.c.commune_id)
        & (RiskPrediction.created_at == latest_pred_sq.c.latest_created_at),
    )
    latest_preds = (await db.execute(latest_preds_stmt)).scalars().all()
    risk_critico = sum(1 for p in latest_preds if normalize_category(p.risk_category) == "critico")
    risk_alto = sum(1 for p in latest_preds if normalize_category(p.risk_category) == "alto")

    today = datetime.now(timezone.utc).date()
    start_30 = today - timedelta(days=30)
    start_14 = today - timedelta(days=14)
    start_7 = today - timedelta(days=7)

    # `fecha` es texto libre (formatos variados) → no se puede filtrar en SQL de
    # forma confiable. Pre-filtramos por `ingested_at` para acotar el scan: un
    # evento con fecha en los últimos 30 días no pudo ingestarse hace 30+ días.
    start_30_dt = datetime.now(timezone.utc) - timedelta(days=30)
    events_30 = (
        (await db.execute(select(LandslideEvent).where(LandslideEvent.ingested_at >= start_30_dt)))
        .scalars()
        .all()
    )
    total_events_30d = 0
    for e in events_30:
        d = _safe_parse_date(e.fecha)
        if d and d >= start_30:
            total_events_30d += 1

    recent_preds = (
        (await db.execute(select(RiskPrediction).where(RiskPrediction.created_at >= start_14)))
        .scalars()
        .all()
    )
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
    # Acota a predicciones recientes (evita el full table scan que traía TODA la
    # tabla) y filtra con is_alert_category(), que es insensible a tildes y
    # mayúsculas. Antes comparaba contra {"Alto","Crítico"} capitalizados
    # mientras la BD guarda "alto"/"critico" → las alertas NUNCA aparecían.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(RiskPrediction)
        .where(RiskPrediction.created_at >= cutoff)
        .order_by(RiskPrediction.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    by_cid = {cid: name for cid, name, _ in _COMUNAS_BASE}
    alerts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        if r.commune_id in seen:
            continue
        seen.add(r.commune_id)  # nos quedamos con la predicción más reciente por comuna
        if not is_alert_category(r.risk_category):
            continue
        alerts.append(
            {
                "id": r.id,
                "commune_id": r.commune_id,
                "nombre_comuna": by_cid.get(r.commune_id, r.commune_id),
                "nivel": alert_level(r.risk_category),
                "precipitacion_7d": 0,
                "n_eventos_recientes": None,
                "fecha_alerta": r.created_at.isoformat() if r.created_at else None,
            }
        )
    alerts.sort(key=lambda a: 0 if a["nivel"] == "Rojo" else 1)
    return alerts[:10]


@router.post(
    "/predict-all",
    dependencies=[Depends(require_token), Depends(rate_limit("predict", times=5, seconds=60))],
)
async def run_predict_all(
    request: Request, db: AsyncSession = Depends(get_async_db)
) -> dict[str, str]:
    from api.audit import log_audit_event

    log_audit_event(
        session=db,
        request=request,
        action="predict_all",
        resource="communes:all",
        summary="Predicción manual de las 21 comunas",
    )
    await predict_all_comunas(db)
    return {"status": "accepted"}


@router.post(
    "/predict-commune",
    dependencies=[Depends(require_token), Depends(rate_limit("predict", times=5, seconds=60))],
)
async def run_predict_commune(
    body: PredictCommuneBody,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, Any]:
    from api.audit import log_audit_event

    log_audit_event(
        session=db,
        request=request,
        action="predict_commune",
        resource=f"commune:{body.commune_id}",
        payload=body.model_dump(),
        summary=f"Predicción manual de la comuna {body.commune_id}",
    )
    result = await predict_risk_stub(body.commune_id, db)
    await db.commit()
    return result


@router.get("/observability/predictions")
async def get_prediction_metrics(
    limit: int = 100, db: AsyncSession = Depends(get_async_db)
) -> dict[str, Any]:
    """Observability: recent prediction logs from DB for drift detection and monitoring."""
    result = await db.execute(
        select(RiskPrediction).order_by(RiskPrediction.created_at.desc()).limit(limit)
    )
    predictions = result.scalars().all()
    predictions.reverse()

    if not predictions:
        return {"total": 0, "predictions": []}

    risk_by_category = {"bajo": 0, "medio": 0, "alto": 0, "critico": 0}
    avg_score = 0.0
    for pred in predictions:
        category = str(pred.risk_category or "").lower()
        if category in risk_by_category:
            risk_by_category[category] += 1
        avg_score += float(pred.risk_score or 0)

    logs = [
        {
            "timestamp": pred.created_at.isoformat() if pred.created_at else None,
            "commune_id": pred.commune_id,
            "risk_score": pred.risk_score,
            "risk_category": pred.risk_category,
            "model_version": pred.model_version,
        }
        for pred in predictions
    ]

    return {
        "total": len(predictions),
        "summary": {
            "risk_distribution": risk_by_category,
            "avg_risk_score": round(avg_score / len(predictions), 3) if predictions else 0,
        },
        "predictions": logs,
    }
