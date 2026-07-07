"""
Feature ML de actividad sísmica reciente.

Un sismo cerca del valle, sobre suelo ya saturado por lluvia, es un disparador
clásico de deslizamientos. Esta señal se resume en un escalar por corrida:

    intensidad = Σ  magnitud² × atenuación_distancia × decaimiento_temporal

- atenuación_distancia: 1 / (1 + (d_km / 50)²) desde el centro del valle —
  un sismo M5 a 200 km pesa menos que un M3 a 15 km.
- decaimiento temporal: 0.9^días — el efecto de un sismo sobre laderas
  inestables se disipa en días/semanas.

El valle mide ~15 km de lado y los epicentros suelen estar a decenas o
cientos de km, así que la diferencia entre comunas es despreciable: el valor
es único para todo el valle y se replica en cada comuna como la clave
`seismic_recent_intensity` del JSON `features` (FeatureBuilder la recoge
automáticamente al reentrenar).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.seismic_event import SeismicEvent
from scraper.commune import haversine_km

FEATURE_KEY = "seismic_recent_intensity"

# Centro aproximado del Valle de Aburrá (Medellín).
VALLEY_LAT = 6.2442
VALLEY_LON = -75.5812

TIME_DECAY_PER_DAY = 0.9
DISTANCE_SCALE_KM = 50.0
WINDOW_DAYS = 30


async def seismic_recent_intensity(session: AsyncSession) -> float:
    """Intensidad sísmica reciente del valle (0.0 si no hay sismos en 30 días)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    stmt = select(SeismicEvent).where(SeismicEvent.event_local_at >= cutoff)
    rows = (await session.execute(stmt)).scalars().all()

    # Un sismo aparece una vez por estación que lo registró: deduplicar.
    seen: set[tuple] = set()
    total = 0.0
    for r in rows:
        key = (r.event_local_at.isoformat() if r.event_local_at else None, r.epicenter_label)
        if key in seen:
            continue
        seen.add(key)
        if r.magnitude is None or r.event_local_at is None:
            continue
        if r.epicenter_lat is not None and r.epicenter_lon is not None:
            d_km = haversine_km(VALLEY_LON, VALLEY_LAT, r.epicenter_lon, r.epicenter_lat)
        else:
            d_km = DISTANCE_SCALE_KM  # sin coordenadas: atenuación media
        days_ago = max(0.0, (now - r.event_local_at).total_seconds() / 86400.0)
        attenuation = 1.0 / (1.0 + (d_km / DISTANCE_SCALE_KM) ** 2)
        total += (r.magnitude**2) * attenuation * (TIME_DECAY_PER_DAY**days_ago)

    return round(total, 4)
