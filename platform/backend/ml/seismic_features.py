"""
ML feature for recent seismic activity.

An earthquake near the valley, on soil already saturated by rain, is a
classic landslide trigger. The signal is summarized into one scalar per
commune:

    intensity = Σ  magnitude² × distance_attenuation × time_decay

- distance_attenuation: 1 / (1 + (d_km / 50)²), with d_km measured from EACH
  COMMUNE'S CENTROID to the epicenter (not from a single valley center): an
  earthquake with an epicenter on the western edge weighs more for San
  Javier (13) than for Santa Elena (90), ~20 km to the east.
- time decay: 0.9^days — the effect of an earthquake on unstable slopes
  dissipates over days/weeks.

Centroids come from `domain/communes.py::CENTROIDS` (all 21, extracted from
official cartography) and get overridden with `centroid_lat`/`centroid_lon`
from MLFeature.features once `scraper/medellin_datos.py` has written them.
They used to be read ONLY from the DB, so without that scraper all 21
communes fell back to the valley's center and the per-commune signal
silently became a constant.

The key travels as `seismic_recent_intensity` in MLFeature's `features`
JSON (FeatureBuilder picks it up automatically on retrain).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ml_feature import MLFeature
from db.models.seismic_event import SeismicEvent
from domain.communes import CENTROIDS, VALLEY_CENTROID
from infrastructure.external.arcgis_client import haversine_km

FEATURE_KEY = "seismic_recent_intensity"

# Center of the Valle de Aburrá. With CENTROIDS covering all 21 communes,
# this now only applies to an unknown id, never a real commune.
VALLEY_LAT, VALLEY_LON = VALLEY_CENTROID

TIME_DECAY_PER_DAY = 0.9
DISTANCE_SCALE_KM = 50.0
WINDOW_DAYS = 30


async def _centroids_by_commune(session: AsyncSession) -> dict[str, tuple[float, float]]:
    """(lat, lon) per commune: static seed + override from scraped data.

    The seed is `domain.communes.CENTROIDS` (all 21, from official
    cartography). On top of that, whatever is in `MLFeature.features` gets
    applied, most recent row first.

    This function used to read ONLY from `ml_features`, so on a base where
    `scraper/medellin_datos.py` hadn't run it returned `{}` and all 21
    communes fell back to the valley's center — the per-commune seismic
    signal turned into a constant with nothing flagging it.
    """
    out: dict[str, tuple[float, float]] = dict(CENTROIDS)

    stmt = (
        select(MLFeature.commune_id, MLFeature.features)
        .where(MLFeature.features.isnot(None))
        .order_by(MLFeature.reference_date.desc().nulls_last())
    )
    scraped: set[str] = set()
    for commune_id, features in (await session.execute(stmt)).all():
        cid = str(commune_id)
        if cid in scraped or not isinstance(features, dict):
            continue
        lat, lon = features.get("centroid_lat"), features.get("centroid_lon")
        if lat is not None and lon is not None:
            out[cid] = (float(lat), float(lon))
            scraped.add(cid)
    return out


async def _recent_unique_events(session: AsyncSession) -> list[SeismicEvent]:
    """Earthquakes from the last WINDOW_DAYS, deduplicated (an earthquake
    appears once per station that recorded it)."""
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
            d_km = DISTANCE_SCALE_KM  # no coordinates: average attenuation
        days_ago = max(0.0, (now - r.event_local_at).total_seconds() / 86400.0)
        attenuation = 1.0 / (1.0 + (d_km / DISTANCE_SCALE_KM) ** 2)
        total += (r.magnitude**2) * attenuation * (TIME_DECAY_PER_DAY**days_ago)
    return round(total, 4)


async def seismic_intensity_by_commune(session: AsyncSession) -> dict[str, float]:
    """Recent seismic intensity per commune (empty dict if no earthquakes)."""
    events = await _recent_unique_events(session)
    if not events:
        return {}
    now = datetime.now(timezone.utc)
    centroids = await _centroids_by_commune(session)
    out: dict[str, float] = {}
    for cid, (lat, lon) in centroids.items():
        out[cid] = _intensity_at(lat, lon, events, now)
    # Valley value as a fallback for communes with no known centroid.
    out["_default"] = _intensity_at(VALLEY_LAT, VALLEY_LON, events, now)
    return out


async def seismic_recent_intensity(session: AsyncSession) -> float:
    """Valley-wide seismic intensity (single scalar). Kept for
    compatibility; the per-commune signal is in seismic_intensity_by_commune."""
    events = await _recent_unique_events(session)
    if not events:
        return 0.0
    return _intensity_at(VALLEY_LAT, VALLEY_LON, events, datetime.now(timezone.utc))
