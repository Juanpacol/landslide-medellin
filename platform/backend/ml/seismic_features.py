"""
Feature ML de actividad sísmica reciente.

Un sismo cerca del valle, sobre suelo ya saturado por lluvia, es un disparador
clásico de deslizamientos. La señal se resume en un escalar por comuna:

    intensidad = Σ  magnitud² × atenuación_distancia × decaimiento_temporal

- atenuación_distancia: 1 / (1 + (d_km / 50)²), con d_km medido desde el
  CENTROIDE DE CADA COMUNA al epicentro (no desde un centro único del valle):
  un sismo con epicentro en el borde occidental pesa más en San Javier (13)
  que en Santa Elena (90), ~20 km al oriente.
- decaimiento temporal: 0.9^días — el efecto de un sismo sobre laderas
  inestables se disipa en días/semanas.

Los centroides se reusan de `centroid_lat`/`centroid_lon` que ya escribe
`scraper/medellin_datos.py` en MLFeature.features (mismo criterio que
`alerts/evacuation.py::_commune_centroid`). Comuna sin centroide conocido →
fallback al centro del valle (comportamiento anterior).

La clave viaja como `seismic_recent_intensity` en el JSON `features` de
MLFeature (FeatureBuilder la recoge automáticamente al reentrenar).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.seismic_event import SeismicEvent
from infrastructure.external.arcgis_client import haversine_km

FEATURE_KEY = "seismic_recent_intensity"

# Centro aproximado del Valle de Aburrá (fallback si la comuna no tiene centroide).
VALLEY_LAT = 6.2442
VALLEY_LON = -75.5812

TIME_DECAY_PER_DAY = 0.9
DISTANCE_SCALE_KM = 50.0
WINDOW_DAYS = 30


async def _centroids_by_commune(session: AsyncSession) -> dict[str, tuple[float, float]]:
    """(lat, lon) por comuna desde MLFeature.features, fila más reciente primero."""
    stmt = (
        select(MLFeature.commune_id, MLFeature.features)
        .where(MLFeature.features.isnot(None))
        .order_by(MLFeature.reference_date.desc().nulls_last())
    )
    out: dict[str, tuple[float, float]] = {}
    for commune_id, features in (await session.execute(stmt)).all():
        cid = str(commune_id)
        if cid in out or not isinstance(features, dict):
            continue
        lat, lon = features.get("centroid_lat"), features.get("centroid_lon")
        if lat is not None and lon is not None:
            out[cid] = (float(lat), float(lon))
    return out


async def _recent_unique_events(session: AsyncSession) -> list[SeismicEvent]:
    """Sismos de los últimos WINDOW_DAYS, deduplicados (un sismo aparece una
    vez por estación que lo registró)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    stmt = select(SeismicEvent).where(SeismicEvent.event_local_at >= cutoff)
    rows = (await session.execute(stmt)).scalars().all()

    seen: set[tuple] = set()
    unique: list[SeismicEvent] = []
    for r in rows:
        key = (r.event_local_at.isoformat() if r.event_local_at else None, r.epicenter_label)
        if key in seen:
            continue
        seen.add(key)
        if r.magnitude is None or r.event_local_at is None:
            continue
        unique.append(r)
    return unique


def _intensity_at(lat: float, lon: float, events: list[SeismicEvent], now: datetime) -> float:
    total = 0.0
    for r in events:
        if r.epicenter_lat is not None and r.epicenter_lon is not None:
            d_km = haversine_km(lon, lat, r.epicenter_lon, r.epicenter_lat)
        else:
            d_km = DISTANCE_SCALE_KM  # sin coordenadas: atenuación media
        days_ago = max(0.0, (now - r.event_local_at).total_seconds() / 86400.0)
        attenuation = 1.0 / (1.0 + (d_km / DISTANCE_SCALE_KM) ** 2)
        total += (r.magnitude**2) * attenuation * (TIME_DECAY_PER_DAY**days_ago)
    return round(total, 4)


async def seismic_intensity_by_commune(session: AsyncSession) -> dict[str, float]:
    """Intensidad sísmica reciente por comuna (dict vacío si no hay sismos)."""
    events = await _recent_unique_events(session)
    if not events:
        return {}
    now = datetime.now(timezone.utc)
    centroids = await _centroids_by_commune(session)
    out: dict[str, float] = {}
    for cid, (lat, lon) in centroids.items():
        out[cid] = _intensity_at(lat, lon, events, now)
    # Valor de valle como fallback para comunas sin centroide conocido.
    out["_default"] = _intensity_at(VALLEY_LAT, VALLEY_LON, events, now)
    return out


async def seismic_recent_intensity(session: AsyncSession) -> float:
    """Intensidad sísmica del valle (escalar único). Se mantiene para
    compatibilidad; la señal por comuna está en seismic_intensity_by_commune."""
    events = await _recent_unique_events(session)
    if not events:
        return 0.0
    return _intensity_at(VALLEY_LAT, VALLEY_LON, events, datetime.now(timezone.utc))
