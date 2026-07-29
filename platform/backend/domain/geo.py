"""
Geometría pura. Sin I/O, sin dependencias externas — solo `math`.

Vivía en `infrastructure/external/arcgis_client.py`, que importa `httpx` y
`scraper.common`. Como `domain/` no puede importar nada con I/O (regla de capas
de CLAUDE.md), tener aquí las funciones puras es lo que permite que
`domain/seismic_dedup.py` calcule distancias sin arrastrar un cliente HTTP a la
capa de dominio. `arcgis_client` re-exporta `haversine_km` para no romper a sus
importadores actuales.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distancia en km entre dos puntos.

    ⚠️ El orden es **LON primero**, por compatibilidad con los llamadores que ya
    existen (GeoJSON y ArcGIS usan `[lon, lat]`). En Medellín lat≈6.2 y
    lon≈−75.5, así que invertir los argumentos NO lanza ningún error: devuelve
    una distancia equivocada pero plausible, que es el peor fallo posible.
    Si tienes lat/lon a mano, usa `distance_km`, que es keyword-only.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def distance_km(*, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Igual que `haversine_km` pero **keyword-only**: imposible invertir el orden.

    Es la que debe usarse en código nuevo.
    """
    return haversine_km(lon1, lat1, lon2, lat2)
