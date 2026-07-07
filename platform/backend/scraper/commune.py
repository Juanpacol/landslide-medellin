"""
Shim de compatibilidad — la implementación vive en
infrastructure/external/arcgis_client.py.

Todos los scrapers y ml/seismic_features importan de aquí; se mantiene el
módulo para no tocar ~10 imports en el mismo PR (se limpian en PR5).
"""

from infrastructure.external.arcgis_client import (  # noqa: F401
    COMUNA_QUERY_URL,
    _CORREG_TO_ML,
    haversine_km,
    lookup_commune_for_point,
    official_to_ml_commune,
    parse_ml_commune_from_siata_field,
    ring_centroid_lonlat,
)
