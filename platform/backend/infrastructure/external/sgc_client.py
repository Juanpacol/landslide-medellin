"""
Cliente del feed sísmico del Servicio Geológico Colombiano (SGC).

## Por qué el SGC y no solo USGS

Medido el 2026-07-29 sobre el bounding box del Valle de Aburrá
(-76.0,5.8)-(-75.2,6.6), julio 2026 completo y **sin umbral de magnitud**:
USGS devuelve **0 eventos**; el SGC registró **9**. El umbral de detección de
USGS en Antioquia está muy por encima de lo que dispara un deslizamiento
cosísmico local. El SGC es la fuente primaria; USGS, la red de seguridad para
eventos regionales grandes.

Y hace falta ya: el feed de SIATA lleva sin producir eventos nuevos desde el
2026-03-01 mientras el scraper reporta `ok` en cada corrida, porque
`records_valid=0` es indistinguible de "el parser dejó de encajar".

## El endpoint no está documentado

No hay documentación pública. La URL base se extrajo del bundle de React de
`https://www.sgc.gov.co/sismos` (`/static/js/main.*.js`), donde la constante es
`https://api.sgc.gov.co/`. Verificado contra el servidor real: HTTP 200,
`access-control-allow-origin: *`, sin API key y sin registro. Corre sobre API
Gateway + Lambda.

## Dos trampas confirmadas empíricamente

1. **Un HTTP 200 puede traer un cuerpo de error.** Ventanas de ~210 días
   devuelven `{"errorType":"Sandbox.Timedout", ...}` **con status 200**. Hay que
   validar el CUERPO, no el código de estado. De ahí `SgcFeedError`.
2. **No admite bbox ni magnitud mínima.** Devuelve el país entero; el filtrado
   espacial es responsabilidad del llamador. Ventanas ≤30 días van bien
   (probado: 30 días → 2.084 eventos).

## Zonas horarias y escalas

`utcTime` y `localTime` son el mismo instante: `"2026-07-25 05:20:43"` en UTC y
`"2026-07-25 00:20:43"` en America/Bogota. Se usa `utcTime` y se marca como
tz-aware. `magType` es `MLr`/`MLr_1..4`/`MLr_vmm` (ML regional con calibración
por región del SGC), **no comparable con el `mb` de USGS** — por eso
`seismic_events.mag_type` existe y la magnitud de consenso del clúster es la del
ganador de precedencia, nunca una media.

`geometry.coordinates` es `[lon, lat, depth_km]` — orden GeoJSON, no invertir.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from scraper.common import with_retries

logger = logging.getLogger(__name__)

SOURCE_KEY = "sgc"

# Override por env solo para pruebas o si el SGC cambia de ruta: es el feed menos
# estable de los tres y no está documentado.
FEED_URL = "https://api.sgc.gov.co/biweekly/biweekly_earthquakes"

# Ventana máxima por petición. Pese al nombre "biweekly" acepta rangos
# arbitrarios, pero por encima de ~30 días la Lambda agota su tiempo y devuelve
# un cuerpo de error con HTTP 200.
MAX_WINDOW_DAYS = 30

# Bounding box del Valle de Aburrá y alrededores. El feed no filtra por
# geografía, así que se recorta aquí: un sismo en Nariño no aporta nada al
# riesgo de deslizamiento en Medellín, y guardarlo solo infla la tabla.
# Generoso a propósito (~150 km): la atenuación por distancia de
# `ml/seismic_features.py` ya se encarga de bajarle el peso a los lejanos.
BBOX_MIN_LAT, BBOX_MAX_LAT = 5.0, 7.5
BBOX_MIN_LON, BBOX_MAX_LON = -76.5, -74.5


class SgcFeedError(RuntimeError):
    """El feed respondió 200 pero el cuerpo no es un FeatureCollection válido."""


def _parse_dt(value: Any) -> datetime | None:
    """`"YYYY-MM-DD HH:MM:SS"` en UTC → datetime tz-aware."""
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
    """¿El epicentro cae en la región de interés? Sin coordenadas → False."""
    if lat is None or lon is None:
        return False
    return BBOX_MIN_LAT <= lat <= BBOX_MAX_LAT and BBOX_MIN_LON <= lon <= BBOX_MAX_LON


def parse_feature(feat: dict[str, Any]) -> dict[str, Any] | None:
    """Un Feature del SGC → fila de `seismic_events`. Puro y tolerante.

    Devuelve None si falta lo imprescindible (id, tiempo de origen o magnitud):
    la intensidad sísmica es una Σ de magnitud², así que una fila sin magnitud no
    aporta nada, y sin tiempo no se puede agrupar en un evento canónico.
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

    # GeoJSON: [lon, lat, depth_km]. El orden importa y es fácil de invertir.
    lon = _as_float(coords[0]) if len(coords) > 0 else None
    lat = _as_float(coords[1]) if len(coords) > 1 else None
    depth = _as_float(coords[2]) if len(coords) > 2 else _as_float(props.get("depth"))

    # `place` es "Municipio - Departamento, País"; `closerTowns` trae hasta 3
    # municipios con distancia y es más informativo para una alerta.
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
    """FeatureCollection → filas. Lanza `SgcFeedError` si el cuerpo no es válido.

    Esta validación es la que atrapa el `{"errorType": "Sandbox.Timedout"}` que
    el SGC devuelve **con HTTP 200** cuando la ventana es demasiado larga. Sin
    ella, una ventana grande parecería "cero sismos" en vez de un fallo.
    """
    if not isinstance(payload, dict):
        raise SgcFeedError(f"respuesta no es un objeto JSON: {type(payload).__name__}")
    if payload.get("errorType") or payload.get("errorMessage"):
        raise SgcFeedError(
            f"error del servidor con HTTP 200: {payload.get('errorType')} "
            f"{str(payload.get('errorMessage'))[:120]}"
        )
    features = payload.get("features")
    if features is None or not isinstance(features, list):
        raise SgcFeedError(f"sin lista 'features'; claves={sorted(payload)[:6]}")

    rows: list[dict[str, Any]] = []
    for feat in features:
        row = parse_feature(feat)
        if row is not None:
            rows.append(row)
    return rows


async def fetch_events(
    client: httpx.AsyncClient, *, start: date, end: date
) -> list[dict[str, Any]]:
    """Sismos del SGC en `[start, end]`, ya recortados al bounding box.

    El cliente se INYECTA (mismo criterio que `arcgis_client`): quien llama es
    dueño del pool de conexiones.
    """
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError(
            f"ventana de {(end - start).days} días supera el máximo de "
            f"{MAX_WINDOW_DAYS}; el feed devolvería un timeout con HTTP 200"
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
    """Ventana reciente. `today` es inyectable para poder testear."""
    end = today or datetime.now(timezone.utc).date()
    # +1 día de margen por si el SGC publica con la fecha local de Bogotá.
    return await fetch_events(client, start=end - timedelta(days=days), end=end + timedelta(days=1))
