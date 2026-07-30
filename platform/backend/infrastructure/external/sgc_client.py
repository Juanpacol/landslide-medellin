"""
Colombian Geological Survey (SGC) seismic feed client.

## Why SGC and not just USGS

Measured on 2026-07-29 over the Valle de Aburrá bounding box
(-76.0,5.8)-(-75.2,6.6), all of July 2026, **with no magnitude threshold**:
USGS returns **0 events**; SGC recorded **9**. USGS's detection threshold
in Antioquia is far above what triggers a local coseismic landslide. SGC is
the primary source; USGS is the safety net for large regional events.

And it's needed now: the SIATA feed hasn't produced a new event since
2026-03-01 while the scraper reports `ok` on every run, because
`records_valid=0` is indistinguishable from "the parser stopped matching".

## The endpoint isn't documented

No public documentation. The base URL was extracted from the React bundle
of `https://www.sgc.gov.co/sismos` (`/static/js/main.*.js`), where the
constant is `https://api.sgc.gov.co/`. Verified against the real server:
HTTP 200, `access-control-allow-origin: *`, no API key, no registration.
Runs on API Gateway + Lambda.

## Two empirically confirmed traps

1. **An HTTP 200 can carry an error body.** ~210-day windows return
   `{"errorType":"Sandbox.Timedout", ...}` **with status 200**. You have to
   validate the BODY, not the status code. Hence `SgcFeedError`.
2. **No bbox or minimum-magnitude support.** Returns the whole country;
   spatial filtering is the caller's responsibility. Windows ≤30 days work
   fine (tested: 30 days → 2,084 events).

## Timezones and scales

`utcTime` and `localTime` are the same instant: `"2026-07-25 05:20:43"` in
UTC and `"2026-07-25 00:20:43"` in America/Bogota. `utcTime` is used and
marked tz-aware. `magType` is `MLr`/`MLr_1..4`/`MLr_vmm` (regional ML with
SGC's per-region calibration), **not comparable to USGS's `mb`** — that's
why `seismic_events.mag_type` exists and the cluster's consensus magnitude
is the precedence winner's, never a mean.

`geometry.coordinates` is `[lon, lat, depth_km]` — GeoJSON order, don't invert.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from scraper.common import with_retries

logger = logging.getLogger(__name__)

SOURCE_KEY = "sgc"

# Env override only for tests or if SGC changes its route: it's the least
# stable of the three feeds and it's undocumented.
FEED_URL = "https://api.sgc.gov.co/biweekly/biweekly_earthquakes"

# Max window per request. Despite the name "biweekly" it accepts arbitrary
# ranges, but above ~30 days the Lambda times out and returns an error body
# with HTTP 200.
MAX_WINDOW_DAYS = 30

# Bounding box for the Valle de Aburrá and surroundings. The feed doesn't
# filter by geography, so it's trimmed here: an earthquake in Nariño adds
# nothing to Medellín's landslide risk, and storing it only bloats the
# table. Deliberately generous (~150 km): `ml/seismic_features.py`'s
# distance attenuation already handles downweighting the far ones.
BBOX_MIN_LAT, BBOX_MAX_LAT = 5.0, 7.5
BBOX_MIN_LON, BBOX_MAX_LON = -76.5, -74.5


class SgcFeedError(RuntimeError):
    """The feed responded 200 but the body isn't a valid FeatureCollection."""


def _parse_dt(value: Any) -> datetime | None:
    """`"YYYY-MM-DD HH:MM:SS"` in UTC → tz-aware datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def in_bbox(lat: float | None, lon: float | None) -> bool:
    """Does the epicenter fall in the region of interest? No coordinates → False."""
    if lat is None or lon is None:
        return False
    return BBOX_MIN_LAT <= lat <= BBOX_MAX_LAT and BBOX_MIN_LON <= lon <= BBOX_MAX_LON


def parse_feature(feat: dict[str, Any]) -> dict[str, Any] | None:
    """An SGC Feature → `seismic_events` row. Pure and tolerant.

    Returns None if something essential is missing (id, origin time, or
    magnitude): seismic intensity is a Σ of magnitude², so a row with no
    magnitude contributes nothing, and without a time it can't be grouped
    into a canonical event.
    """
    if not isinstance(feat, dict):
        return None
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates") or []

    event_id = feat.get("id") or props.get("id")
    if not event_id:
        return None

    event_at = _parse_dt(props.get("utcTime"))
    magnitude = _as_float(props.get("mag"))
    if event_at is None or magnitude is None:
        return None

    # GeoJSON: [lon, lat, depth_km]. Order matters and is easy to invert.
    lon = _as_float(coords[0]) if len(coords) > 0 else None
    lat = _as_float(coords[1]) if len(coords) > 1 else None
    depth = _as_float(coords[2]) if len(coords) > 2 else _as_float(props.get("depth"))

    # `place` is "Municipality - Department, Country"; `closerTowns` carries
    # up to 3 municipalities with distance and is more informative for an alert.
    label = props.get("place") or props.get("closerTowns")

    return {
        "source_row_id": f"{SOURCE_KEY}:{event_id}",
        "source": SOURCE_KEY,
        "event_local_at": event_at,
        "magnitude": magnitude,
        "mag_type": props.get("magType"),
        "depth_km": depth,
        "epicenter_lat": lat,
        "epicenter_lon": lon,
        "epicenter_label": str(label) if label else None,
    }


def parse_feed(payload: Any) -> list[dict[str, Any]]:
    """FeatureCollection → rows. Raises `SgcFeedError` if the body isn't valid.

    This validation is what catches the `{"errorType": "Sandbox.Timedout"}`
    SGC returns **with HTTP 200** when the window is too long. Without it,
    a large window would look like "zero earthquakes" instead of a failure.
    """
    if not isinstance(payload, dict):
        raise SgcFeedError(f"response is not a JSON object: {type(payload).__name__}")
    if payload.get("errorType") or payload.get("errorMessage"):
        raise SgcFeedError(
            f"server error with HTTP 200: {payload.get('errorType')} "
            f"{str(payload.get('errorMessage'))[:120]}"
        )
    features = payload.get("features")
    if features is None or not isinstance(features, list):
        raise SgcFeedError(f"no 'features' list; keys={sorted(payload)[:6]}")

    rows: list[dict[str, Any]] = []
    for feat in features:
        row = parse_feature(feat)
        if row is not None:
            rows.append(row)
    return rows


async def fetch_events(
    client: httpx.AsyncClient, *, start: date, end: date
) -> list[dict[str, Any]]:
    """SGC earthquakes in `[start, end]`, already trimmed to the bounding box.

    The client is INJECTED (same criterion as `arcgis_client`): the caller
    owns the connection pool.
    """
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"{(end - start).days}-day window exceeds the {MAX_WINDOW_DAYS}-day "
            "max; the feed would return a timeout with HTTP 200"
        )

    params = {"startdate": start.isoformat(), "enddate": end.isoformat()}

    async def _call() -> Any:
        r = await client.get(FEED_URL, params=params)
        r.raise_for_status()
        return r.json()

    rows = parse_feed(await with_retries(_call))
    return [r for r in rows if in_bbox(r["epicenter_lat"], r["epicenter_lon"])]


async def fetch_recent(
    client: httpx.AsyncClient, *, days: int = 2, today: date | None = None
) -> list[dict[str, Any]]:
    """Recent window. `today` is injectable so it can be tested."""
    end = today or datetime.now(timezone.utc).date()
    # +1 day margin in case SGC publishes with Bogotá's local date.
    return await fetch_events(client, start=end - timedelta(days=days), end=end + timedelta(days=1))
