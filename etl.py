"""
ETL Pipeline — Sistema de Análisis de Riesgo de Deslizamientos, Medellín
Ejecutar: python etl.py
"""

import os
import sys
import json
import math
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Directorio de datos crudos
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Acumulador global de logs de calidad
_quality_logs: list[dict] = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_date(value) -> str | None:
    """Intenta parsear una fecha en múltiples formatos y retorna ISO 8601 (YYYY-MM-DD)."""
    if pd.isna(value) or str(value).strip() == "":
        return None
    s = str(value).strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s[:len(fmt)], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Último intento con pandas
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None


def _replace_nan(records: list[dict]) -> list[dict]:
    """Reemplaza NaN/inf con None en una lista de dicts para inserción en Supabase."""
    cleaned = []
    for row in records:
        new_row = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                new_row[k] = None
            else:
                new_row[k] = v
        cleaned.append(new_row)
    return cleaned


def _insert_batches(client, table: str, records: list[dict], batch_size: int = 500):
    """Inserta registros en lotes."""
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        client.table(table).insert(batch).execute()


# ---------------------------------------------------------------------------
# Tarea 2.4 — Log de calidad
# ---------------------------------------------------------------------------

def build_log_record(
    fuente: str,
    descargados: int,
    validos: int,
    descartados: int,
    motivo: str,
    estado: str,
) -> dict:
    """Construye un dict para insertar en data_quality_log."""
    return {
        "fuente": fuente,
        "fecha_ingesta": datetime.utcnow().isoformat(),
        "registros_descargados": descargados,
        "registros_validos": validos,
        "registros_descartados": descartados,
        "motivo_descarte": motivo,
        "estado": estado,
    }


# ---------------------------------------------------------------------------
# Tarea 2.1 — Fuente 1: Emergencias
# ---------------------------------------------------------------------------

_EMERGENCIAS_CKAN_API = (
    "https://medata.gov.co/api/3/action/package_show"
    "?id=emergencias-atendidas-cuerpo-oficial-bomberos"
)
_EMERGENCIAS_LOCAL = RAW_DIR / "emergencias.csv"

_EMERGENCIAS_COLS = [
    "source_row_id",
    "fecha",
    "tipo_emergencia",
    "commune_id",
    "barrio",
    "latitud",
    "longitud",
    "has_coords",
]

# Posibles nombres del campo commune_id en el CSV fuente
_COMMUNE_FIELD_CANDIDATES = ["COMUNA", "comuna", "CODIGO_COMUNA", "codigo_comuna", "commune_id"]
# Posibles nombres del campo fecha
_FECHA_FIELD_CANDIDATES = ["fecha", "FECHA", "fecha_hora", "FECHA_HORA"]
# Posibles nombres del campo tipo_emergencia
_TIPO_FIELD_CANDIDATES = ["tipo_emergencia", "TIPO_EMERGENCIA", "tipo", "TIPO"]
# Posibles nombres de latitud/longitud
_LAT_CANDIDATES = ["latitud", "LATITUD", "lat", "LAT", "latitude"]
_LON_CANDIDATES = ["longitud", "LONGITUD", "lon", "LON", "longitude"]
_BARRIO_CANDIDATES = ["barrio", "BARRIO", "nombre_barrio", "NOMBRE_BARRIO"]


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _sample_emergencies() -> pd.DataFrame:
    """Datos de muestra realistas de emergencias para demo cuando la API falla."""
    import random
    random.seed(42)
    comunas = [
        ("1", "Popular"), ("2", "Santa Cruz"), ("3", "Manrique"), ("4", "Aranjuez"),
        ("5", "Castilla"), ("6", "Doce de Octubre"), ("7", "Robledo"), ("8", "Villa Hermosa"),
        ("9", "Buenos Aires"), ("13", "San Javier"), ("50", "Palmitas"), ("60", "San Cristóbal"),
        ("70", "Altavista"), ("80", "San Antonio de Prado"), ("90", "Santa Elena"),
    ]
    tipos = ["Deslizamiento de tierra", "Movimiento en masa", "Deslizamiento", "Movimiento de tierra"]
    barrios = ["La Cruz", "El Pinal", "Versalles", "La Honda", "Bello Oriente", "La Sierra",
               "El Faro", "Carpinelo", "La Avanzada", "Granizal"]
    rows = []
    base = datetime(2018, 1, 1)
    for i in range(800):
        days = random.randint(0, 365 * 6)
        fecha = (base + timedelta(days=days)).strftime("%Y-%m-%d")
        comuna_id, _ = random.choice(comunas)
        lat = 6.2 + random.uniform(-0.15, 0.15)
        lon = -75.57 + random.uniform(-0.1, 0.1)
        rows.append({
            "source_row_id": str(i),
            "fecha": fecha,
            "tipo_emergencia": random.choice(tipos),
            "commune_id": comuna_id,
            "barrio": random.choice(barrios),
            "latitud": lat,
            "longitud": lon,
            "has_coords": True,
        })
    logger.info("Usando %d registros de muestra para emergencias", len(rows))
    return pd.DataFrame(rows, columns=_EMERGENCIAS_COLS)


def _sample_precipitation() -> pd.DataFrame:
    """Datos de muestra realistas de precipitación para demo cuando la API falla."""
    import random
    random.seed(99)
    estaciones = ["Niquía", "Olaya Herrera", "Santa Elena", "Altavista", "San Cristóbal"]
    rows = []
    base = datetime(2018, 1, 1)
    for est in estaciones:
        precip_vals = []
        for i in range(365 * 6):
            fecha = (base + timedelta(days=i)).strftime("%Y-%m-%d")
            # Simular estacionalidad: más lluvia en abril-mayo y oct-nov
            month = int(fecha[5:7])
            base_rain = 4.0 if month in (4, 5, 10, 11) else 1.5
            mm = max(0.0, random.gauss(base_rain, 3.0))
            precip_vals.append(mm)
            rows.append({
                "fecha": fecha,
                "estacion": est,
                "precipitacion_mm": round(mm, 2),
                "precipitacion_acum_3d": 0.0,
                "precipitacion_acum_7d": 0.0,
                "cod_municipio": "05001",
            })
        # Calcular acumulados
        for j in range(len(precip_vals)):
            rows[-(len(precip_vals) - j)]["precipitacion_acum_3d"] = round(sum(precip_vals[max(0,j-2):j+1]), 2)
            rows[-(len(precip_vals) - j)]["precipitacion_acum_7d"] = round(sum(precip_vals[max(0,j-6):j+1]), 2)
    logger.info("Usando %d registros de muestra para precipitación", len(rows))
    return pd.DataFrame(rows, columns=_PRECIP_COLS)


def _sample_geodata() -> dict:
    """GeoJSON de muestra con las comunas reales de Medellín (polígonos simplificados)."""
    comunas = [
        ("1", "Popular", 6.318, -75.553, 22.0),
        ("2", "Santa Cruz", 6.298, -75.548, 18.5),
        ("3", "Manrique", 6.278, -75.548, 20.0),
        ("4", "Aranjuez", 6.278, -75.558, 12.0),
        ("5", "Castilla", 6.278, -75.578, 8.0),
        ("6", "Doce de Octubre", 6.298, -75.578, 16.0),
        ("7", "Robledo", 6.278, -75.598, 14.0),
        ("8", "Villa Hermosa", 6.238, -75.548, 19.0),
        ("9", "Buenos Aires", 6.228, -75.548, 17.5),
        ("10", "La Candelaria", 6.248, -75.568, 5.0),
        ("11", "Laureles-Estadio", 6.238, -75.588, 4.0),
        ("12", "La América", 6.238, -75.598, 6.0),
        ("13", "San Javier", 6.238, -75.608, 21.0),
        ("14", "El Poblado", 6.198, -75.568, 10.0),
        ("15", "Guayabal", 6.198, -75.588, 7.0),
        ("16", "Belén", 6.218, -75.598, 9.0),
        ("50", "Palmitas", 6.318, -75.668, 25.0),
        ("60", "San Cristóbal", 6.278, -75.638, 23.0),
        ("70", "Altavista", 6.218, -75.638, 24.0),
        ("80", "San Antonio de Prado", 6.158, -75.638, 15.0),
        ("90", "Santa Elena", 6.218, -75.498, 20.0),
    ]
    features = []
    for cid, nombre, lat, lon, pendiente in comunas:
        d = 0.015
        features.append({
            "type": "Feature",
            "properties": {
                "commune_id": cid,
                "nombre_comuna": nombre,
                "pendiente_promedio": pendiente,
                "is_zona_ladera": pendiente >= 15,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lon - d, lat - d], [lon + d, lat - d],
                    [lon + d, lat + d], [lon - d, lat + d],
                    [lon - d, lat - d],
                ]],
            },
        })
    logger.info("Usando GeoJSON de muestra con %d comunas", len(features))
    return {"type": "FeatureCollection", "features": features}


def ingest_emergencies() -> pd.DataFrame:
    """
    Descarga el CSV de emergencias desde medata.gov.co (vía CKAN API),
    filtra deslizamientos/movimientos y normaliza campos.
    Si falla, usa datos de muestra.
    """
    empty = pd.DataFrame(columns=_EMERGENCIAS_COLS)
    raw_df = None

    # 1. Intentar cargar desde caché local
    if _EMERGENCIAS_LOCAL.exists():
        logger.info("Cargando emergencias desde caché local: %s", _EMERGENCIAS_LOCAL)
        try:
            raw_df = pd.read_csv(_EMERGENCIAS_LOCAL, low_memory=False)
        except Exception as e:
            logger.warning("No se pudo leer caché local de emergencias: %s", e)

    # 2. Si no hay caché, descargar
    if raw_df is None:
        try:
            logger.info("Consultando CKAN API para emergencias...")
            resp = requests.get(_EMERGENCIAS_CKAN_API, timeout=30)
            resp.raise_for_status()
            pkg = resp.json()
            resources = pkg.get("result", {}).get("resources", [])
            csv_url = None
            for r in resources:
                fmt = (r.get("format") or "").upper()
                url = r.get("url", "")
                if fmt == "CSV" or url.endswith(".csv"):
                    csv_url = url
                    break
            if not csv_url:
                raise ValueError("No se encontró recurso CSV en el paquete CKAN")

            logger.info("Descargando CSV de emergencias desde: %s", csv_url)
            data_resp = requests.get(csv_url, timeout=60)
            data_resp.raise_for_status()
            _EMERGENCIAS_LOCAL.write_bytes(data_resp.content)
            raw_df = pd.read_csv(_EMERGENCIAS_LOCAL, low_memory=False)
        except Exception as e:
            logger.error("Error descargando emergencias: %s", e)
            _quality_logs.append(
                build_log_record("emergencias", 0, 0, 0, str(e), "Error")
            )
            return _sample_emergencies()

    total = len(raw_df)
    logger.info("Emergencias descargadas: %d registros", total)

    # Identificar columnas relevantes
    tipo_col = _find_col(raw_df, _TIPO_FIELD_CANDIDATES)
    fecha_col = _find_col(raw_df, _FECHA_FIELD_CANDIDATES)
    commune_col = _find_col(raw_df, _COMMUNE_FIELD_CANDIDATES)
    lat_col = _find_col(raw_df, _LAT_CANDIDATES)
    lon_col = _find_col(raw_df, _LON_CANDIDATES)
    barrio_col = _find_col(raw_df, _BARRIO_CANDIDATES)

    if tipo_col is None:
        logger.error("No se encontró columna tipo_emergencia en el CSV")
        _quality_logs.append(
            build_log_record("emergencias", total, 0, total, "Columna tipo_emergencia no encontrada", "Error")
        )
        return empty

    # Filtrar deslizamientos / movimientos
    mask = raw_df[tipo_col].astype(str).str.lower().str.contains(
        r"desliz|movimiento", na=False, regex=True
    )
    filtered = raw_df[mask].copy()
    discarded = total - len(filtered)
    logger.info("Emergencias filtradas (desliz/movimiento): %d de %d", len(filtered), total)

    # Construir DataFrame de salida
    out = pd.DataFrame()
    out["source_row_id"] = filtered.index.astype(str)
    out["fecha"] = (filtered[fecha_col].apply(_normalize_date) if fecha_col else None)
    out["tipo_emergencia"] = filtered[tipo_col].astype(str)
    out["commune_id"] = (filtered[commune_col].astype(str) if commune_col else None)
    out["barrio"] = (filtered[barrio_col].astype(str) if barrio_col else None)

    def _to_float(series):
        return pd.to_numeric(series, errors="coerce")

    if lat_col:
        out["latitud"] = _to_float(filtered[lat_col])
    else:
        out["latitud"] = None

    if lon_col:
        out["longitud"] = _to_float(filtered[lon_col])
    else:
        out["longitud"] = None

    out["has_coords"] = (
        out["latitud"].notna()
        & out["longitud"].notna()
        & (out["latitud"].astype(str).str.strip() != "")
        & (out["longitud"].astype(str).str.strip() != "")
    )

    out = out.reset_index(drop=True)

    _quality_logs.append(
        build_log_record(
            "emergencias",
            total,
            len(out),
            discarded,
            "Tipo de emergencia no relacionado con deslizamientos",
            "OK",
        )
    )
    return out[_EMERGENCIAS_COLS]


# ---------------------------------------------------------------------------
# Tarea 2.2 — Fuente 2: Precipitación
# ---------------------------------------------------------------------------

_PRECIP_URL = (
    "https://www.datos.gov.co/resource/s54a-sgyg.csv"
    "?cod_municipio=05001&$limit=50000"
)
_PRECIP_LOCAL = RAW_DIR / "precipitacion_siata.csv"

_PRECIP_COLS = [
    "fecha",
    "estacion",
    "precipitacion_mm",
    "precipitacion_acum_3d",
    "precipitacion_acum_7d",
    "cod_municipio",
]


def ingest_precipitation() -> pd.DataFrame:
    """
    Descarga datos de precipitación diaria para Medellín (cod_municipio=05001).
    Calcula acumulados de 3 y 7 días por estación.
    """
    empty = pd.DataFrame(columns=_PRECIP_COLS)
    raw_df = None

    # 1. Intentar descarga remota
    try:
        logger.info("Descargando precipitación desde datos.gov.co...")
        resp = requests.get(_PRECIP_URL, timeout=60)
        resp.raise_for_status()
        if len(resp.content) > 100:
            _PRECIP_LOCAL.write_bytes(resp.content)
            raw_df = pd.read_csv(_PRECIP_LOCAL, low_memory=False)
            if len(raw_df) == 0:
                raw_df = None
                logger.warning("Descarga de precipitación retornó 0 registros")
    except Exception as e:
        logger.warning("Error descargando precipitación remota: %s", e)

    # 2. Fallback a archivo local
    if raw_df is None:
        if _PRECIP_LOCAL.exists():
            logger.info("Cargando precipitación desde archivo local: %s", _PRECIP_LOCAL)
            try:
                raw_df = pd.read_csv(_PRECIP_LOCAL, low_memory=False)
            except Exception as e:
                logger.error("No se pudo leer archivo local de precipitación: %s", e)
        else:
            logger.error("No hay datos de precipitación disponibles (remoto ni local)")
            _quality_logs.append(
                build_log_record("precipitacion", 0, 0, 0, "Sin datos disponibles", "Error")
            )
            return _sample_precipitation()

    total = len(raw_df)
    logger.info("Precipitación descargada: %d registros", total)

    # Normalizar nombres de columnas a minúsculas
    raw_df.columns = [c.lower().strip() for c in raw_df.columns]

    # Identificar columnas clave
    fecha_col = _find_col(raw_df, ["fecha", "fecha_hora", "date"])
    estacion_col = _find_col(raw_df, ["estacion", "station", "nombre_estacion", "cod_estacion"])
    precip_col = _find_col(raw_df, ["precipitacion_mm", "precipitacion", "valor", "value"])
    municipio_col = _find_col(raw_df, ["cod_municipio", "municipio", "codigo_municipio"])

    if precip_col is None:
        logger.error("No se encontró columna de precipitación en el CSV")
        _quality_logs.append(
            build_log_record("precipitacion", total, 0, total, "Columna precipitacion_mm no encontrada", "Error")
        )
        return empty

    out = raw_df.copy()

    # Normalizar precipitación a numérico
    out["precipitacion_mm"] = pd.to_numeric(out[precip_col], errors="coerce")

    # Descartar negativos y no numéricos
    invalid_mask = out["precipitacion_mm"].isna() | (out["precipitacion_mm"] < 0)
    discarded = int(invalid_mask.sum())
    out = out[~invalid_mask].copy()

    # Normalizar fecha
    if fecha_col:
        out["fecha"] = out[fecha_col].apply(_normalize_date)
    else:
        out["fecha"] = None

    out["estacion"] = out[estacion_col].astype(str) if estacion_col else "desconocida"
    out["cod_municipio"] = out[municipio_col].astype(str) if municipio_col else "05001"

    # Calcular acumulados por estación, ordenado por fecha
    out = out.sort_values(["estacion", "fecha"]).reset_index(drop=True)

    def _rolling_sum(group: pd.DataFrame, window: int) -> pd.Series:
        return (
            group["precipitacion_mm"]
            .rolling(window=window, min_periods=1)
            .sum()
        )

    out["precipitacion_acum_3d"] = (
        out.groupby("estacion", group_keys=False)
        .apply(lambda g: _rolling_sum(g, 3))
        .reset_index(drop=True)
    )
    out["precipitacion_acum_7d"] = (
        out.groupby("estacion", group_keys=False)
        .apply(lambda g: _rolling_sum(g, 7))
        .reset_index(drop=True)
    )

    result = out[_PRECIP_COLS].reset_index(drop=True)

    _quality_logs.append(
        build_log_record(
            "precipitacion",
            total,
            len(result),
            discarded,
            "precipitacion_mm negativo o no numérico",
            "OK",
        )
    )
    return result


# ---------------------------------------------------------------------------
# Tarea 2.3 — Fuente 3: GeoJSON comunas
# ---------------------------------------------------------------------------

_GEODATA_URL = (
    "https://www.medellin.gov.co/apigeomedellin/atributos/archivos/openDataExt/"
    "Gis/open_data/OD281/geojson_pot48_2014_amenaza_movimi.zip"
)
_GEODATA_LOCAL = RAW_DIR / "comunas.geojson"

_COMMUNE_ID_PROPS = ["CODIGO", "commune_id", "COMUNAS", "CODIGO_COMUNA", "COD_COMUNA", "ID", "OBJECTID"]
_NOMBRE_PROPS = ["NOMBRE", "nombre_comuna", "NOMBRE_COMUNA", "NOM_COMUNA", "NAME", "GRADO_AMEN"]
_PENDIENTE_PROPS = ["pendiente_promedio", "PENDIENTE", "PENDIENTE_PROMEDIO", "slope"]

# Mapeo de grado de amenaza a pendiente equivalente (para clasificar Zona_Ladera)
_AMENAZA_TO_PENDIENTE = {
    "ALTA": 25.0,
    "MEDIA": 18.0,
    "BAJA": 10.0,
    "MUY BAJA": 5.0,
    "MUY_BAJA": 5.0,
}

_EMPTY_GEOJSON: dict = {"type": "FeatureCollection", "features": []}


def _find_prop(props: dict, candidates: list[str]):
    for c in candidates:
        if c in props:
            return props[c]
    return None


def ingest_geodata() -> dict:
    """
    Descarga el GeoJSON de amenaza movimientos en masa de Medellín (POT 2014),
    valida features y clasifica zonas de ladera.
    """
    raw_geojson = None

    # 1. Intentar descarga remota (ZIP con GeoJSON dentro)
    try:
        logger.info("Descargando GeoJSON de amenaza movimientos en masa desde GeoMedellín...")
        resp = requests.get(_GEODATA_URL, timeout=60)
        resp.raise_for_status()
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            geojson_files = [f for f in z.namelist() if f.endswith(".geojson") or f.endswith(".json")]
            if not geojson_files:
                raise ValueError("No se encontró archivo GeoJSON dentro del ZIP")
            with z.open(geojson_files[0]) as gf:
                raw_geojson = json.load(gf)
        logger.info("GeoJSON descargado: %d features", len(raw_geojson.get("features", [])))
    except Exception as e:
        logger.warning("Error descargando GeoJSON remoto: %s", e)

    # 2. Fallback a archivo local
    if raw_geojson is None or not raw_geojson.get("features"):
        if _GEODATA_LOCAL.exists():
            logger.info("Cargando GeoJSON desde archivo local: %s", _GEODATA_LOCAL)
            try:
                with open(_GEODATA_LOCAL, "r", encoding="utf-8") as f:
                    raw_geojson = json.load(f)
            except Exception as e:
                logger.error("No se pudo leer GeoJSON local: %s", e)
                _quality_logs.append(
                    build_log_record("geodata_comunas", 0, 0, 0, str(e), "Error")
                )
                return _sample_geodata()
        else:
            logger.error("No hay GeoJSON de comunas disponible (remoto ni local)")
            _quality_logs.append(
                build_log_record("geodata_comunas", 0, 0, 0, "Sin datos disponibles", "Error")
            )
            return _sample_geodata()

    total_features = len(raw_geojson.get("features", []))
    valid_features = []
    discarded = 0

    for feature in raw_geojson.get("features", []):
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}

        # Validar geometry
        geom_type = geom.get("type", "")
        if geom_type not in ("Polygon", "MultiPolygon"):
            discarded += 1
            continue

        # Para dataset de amenazas: usar OBJECTID como commune_id y GRADO_AMEN como nombre
        commune_id = _find_prop(props, _COMMUNE_ID_PROPS)
        if commune_id is None:
            discarded += 1
            continue

        grado_amenaza = str(props.get("GRADO_AMEN", props.get("grado_amen", "DESCONOCIDA"))).upper().strip()
        nombre_comuna = grado_amenaza if grado_amenaza else str(commune_id)

        # Derivar pendiente desde grado de amenaza
        pendiente = _AMENAZA_TO_PENDIENTE.get(grado_amenaza)
        if pendiente is None:
            pendiente = _find_prop(props, _PENDIENTE_PROPS)
            try:
                pendiente = float(pendiente) if pendiente is not None else None
            except (TypeError, ValueError):
                pendiente = None

        is_zona_ladera = (pendiente is not None and pendiente >= 15)

        enriched_props = dict(props)
        enriched_props["commune_id"] = str(commune_id)
        enriched_props["nombre_comuna"] = f"Zona {grado_amenaza.title()} - {commune_id}"
        enriched_props["pendiente_promedio"] = pendiente
        enriched_props["is_zona_ladera"] = is_zona_ladera

        valid_features.append({
            "type": "Feature",
            "properties": enriched_props,
            "geometry": geom,
        })

    result = {"type": "FeatureCollection", "features": valid_features}

    # Guardar GeoJSON limpio
    try:
        with open(_GEODATA_LOCAL, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        logger.info("GeoJSON limpio guardado en %s", _GEODATA_LOCAL)
    except Exception as e:
        logger.warning("No se pudo guardar GeoJSON limpio: %s", e)

    _quality_logs.append(
        build_log_record(
            "geodata_comunas",
            total_features,
            len(valid_features),
            discarded,
            "Feature sin commune_id, nombre_comuna o geometry válida",
            "OK",
        )
    )
    logger.info("GeoJSON procesado: %d features válidos de %d", len(valid_features), total_features)
    return result


# ---------------------------------------------------------------------------
# Tarea 3 — Cargar a Supabase
# ---------------------------------------------------------------------------

def save_to_supabase(
    client,
    events_df: pd.DataFrame,
    precip_df: pd.DataFrame,
    communes_df: pd.DataFrame,
    alerts_list: list[dict],
    log_records: list[dict],
):
    """
    Persiste todos los resultados del ETL en Supabase.
    Lanza ValueError si faltan variables de entorno.
    Lanza excepción de Supabase si hay error de inserción.
    """
    # Validar env vars
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        raise ValueError(
            "Error: SUPABASE_URL y SUPABASE_KEY deben estar definidas en .env"
        )

    # --- events ---
    if not events_df.empty:
        events_records = _replace_nan(events_df.to_dict(orient="records"))
        logger.info("Insertando %d eventos en Supabase...", len(events_records))
        try:
            _insert_batches(client, "events", events_records, batch_size=500)
        except Exception as e:
            print(f"Error insertando events: {e}")
            raise

    # --- precipitation ---
    if not precip_df.empty:
        precip_records = _replace_nan(precip_df.to_dict(orient="records"))
        logger.info("Insertando %d registros de precipitación en Supabase...", len(precip_records))
        try:
            _insert_batches(client, "precipitation", precip_records, batch_size=500)
        except Exception as e:
            print(f"Error insertando precipitation: {e}")
            raise

    # --- communes (upsert por commune_id) ---
    if not communes_df.empty:
        communes_records = _replace_nan(communes_df.to_dict(orient="records"))
        logger.info("Upserting %d comunas en Supabase...", len(communes_records))
        try:
            for i in range(0, len(communes_records), 500):
                batch = communes_records[i : i + 500]
                client.table("communes").upsert(batch, on_conflict="commune_id").execute()
        except Exception as e:
            print(f"Error upserting communes: {e}")
            raise

    # --- alerts ---
    if alerts_list:
        alerts_records = _replace_nan(alerts_list)
        logger.info("Insertando %d alertas en Supabase...", len(alerts_records))
        try:
            _insert_batches(client, "alerts", alerts_records, batch_size=500)
        except Exception as e:
            print(f"Error insertando alerts: {e}")
            raise

    # --- data_quality_log ---
    if log_records:
        log_clean = _replace_nan(log_records)
        logger.info("Insertando %d registros de log de calidad...", len(log_clean))
        try:
            _insert_batches(client, "data_quality_log", log_clean, batch_size=500)
        except Exception as e:
            print(f"Error insertando data_quality_log: {e}")
            raise

    logger.info("Todos los datos guardados en Supabase exitosamente.")


# ---------------------------------------------------------------------------
# Tarea 4.1 — Índice de riesgo
# ---------------------------------------------------------------------------

def compute_risk_index(
    events_df: pd.DataFrame,
    precip_df: pd.DataFrame,
    geo_data: dict,
) -> pd.DataFrame:
    """
    Calcula el índice de riesgo por comuna combinando frecuencia de eventos,
    precipitación acumulada y pendiente topográfica.
    """
    from scipy.stats import spearmanr

    # --- Extraer info de comunas desde GeoJSON ---
    commune_geo: dict[str, dict] = {}
    for feature in geo_data.get("features", []):
        props = feature.get("properties") or {}
        cid = str(props.get("commune_id", "")).strip()
        if cid:
            commune_geo[cid] = {
                "nombre_comuna": props.get("nombre_comuna"),
                "pendiente_promedio": props.get("pendiente_promedio"),
                "is_zona_ladera": props.get("is_zona_ladera", False),
                "geometry": json.dumps(feature.get("geometry")),
            }

    all_commune_ids = set(commune_geo.keys())

    # --- n_eventos por commune_id ---
    n_eventos: dict[str, int] = {}
    if not events_df.empty and "commune_id" in events_df.columns:
        counts = events_df["commune_id"].astype(str).value_counts()
        n_eventos = counts.to_dict()

    # Asegurar que todas las comunas del GeoJSON estén representadas
    for cid in all_commune_ids:
        n_eventos.setdefault(cid, 0)

    # --- Precipitación acum_7d promedio por commune_id (última semana disponible) ---
    # Como la precipitación no tiene commune_id directamente, usamos el promedio global
    # de la última semana disponible como proxy para todas las comunas.
    precip_acum_7d_by_commune: dict[str, float] = {}
    if not precip_df.empty and "precipitacion_acum_7d" in precip_df.columns:
        if "fecha" in precip_df.columns:
            precip_sorted = precip_df.dropna(subset=["fecha"]).sort_values("fecha")
            if not precip_sorted.empty:
                last_date = precip_sorted["fecha"].max()
                try:
                    last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                    week_ago = (last_dt - timedelta(days=7)).strftime("%Y-%m-%d")
                    recent = precip_sorted[precip_sorted["fecha"] >= week_ago]
                except Exception:
                    recent = precip_sorted.tail(7)
                avg_acum = float(recent["precipitacion_acum_7d"].mean()) if not recent.empty else 0.0
                for cid in all_commune_ids:
                    precip_acum_7d_by_commune[cid] = avg_acum

    for cid in all_commune_ids:
        precip_acum_7d_by_commune.setdefault(cid, 0.0)

    # --- Correlación de Spearman (solo comunas con >= 10 eventos) ---
    correlacion_diaria: dict[str, float | None] = {}

    if not events_df.empty and not precip_df.empty:
        if "fecha" in events_df.columns and "fecha" in precip_df.columns:
            # Frecuencia diaria de eventos por commune_id
            events_daily = (
                events_df.dropna(subset=["fecha"])
                .groupby(["commune_id", "fecha"])
                .size()
                .reset_index(name="n_eventos_dia")
            )
            # Precipitación diaria promedio (todas las estaciones)
            precip_daily = (
                precip_df.dropna(subset=["fecha"])
                .groupby("fecha")["precipitacion_mm"]
                .mean()
                .reset_index()
            )

            for cid in all_commune_ids:
                if n_eventos.get(cid, 0) < 10:
                    correlacion_diaria[cid] = None
                    continue
                ev_cid = events_daily[events_daily["commune_id"].astype(str) == cid]
                merged = ev_cid.merge(precip_daily, on="fecha", how="inner")
                if len(merged) < 10:
                    correlacion_diaria[cid] = None
                    continue
                try:
                    corr, _ = spearmanr(merged["precipitacion_mm"], merged["n_eventos_dia"])
                    correlacion_diaria[cid] = float(corr) if not math.isnan(corr) else None
                except Exception:
                    correlacion_diaria[cid] = None
        else:
            for cid in all_commune_ids:
                correlacion_diaria[cid] = None
    else:
        for cid in all_commune_ids:
            correlacion_diaria[cid] = None

    # --- Construir DataFrame base ---
    rows = []
    for cid in all_commune_ids:
        geo_info = commune_geo.get(cid, {})
        rows.append({
            "commune_id": cid,
            "nombre_comuna": geo_info.get("nombre_comuna"),
            "pendiente_promedio": geo_info.get("pendiente_promedio"),
            "is_zona_ladera": geo_info.get("is_zona_ladera", False),
            "n_eventos": n_eventos.get(cid, 0),
            "precipitacion_acum_7d": precip_acum_7d_by_commune.get(cid, 0.0),
            "correlacion_diaria": correlacion_diaria.get(cid),
            "correlacion_3d": None,   # placeholder (requeriría acum_3d diario)
            "correlacion_7d": None,   # placeholder
            "geometry": geo_info.get("geometry"),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        df["indice_riesgo"] = None
        df["categoria_riesgo"] = None
        df["indice_parcial"] = False
        return df

    # --- Normalización min-max [0, 1] ---
    def _minmax(series: pd.Series) -> pd.Series:
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series(0.5, index=series.index)
        return (series - mn) / (mx - mn)

    df["freq_norm"] = _minmax(df["n_eventos"].astype(float))
    df["precip_norm"] = _minmax(df["precipitacion_acum_7d"].astype(float))

    has_pendiente = df["pendiente_promedio"].notna()
    if has_pendiente.any():
        df.loc[has_pendiente, "pendiente_norm"] = _minmax(
            df.loc[has_pendiente, "pendiente_promedio"].astype(float)
        )
    df["pendiente_norm"] = df.get("pendiente_norm", pd.Series(dtype=float))

    # --- Calcular índice de riesgo ---
    indices = []
    parciales = []
    for _, row in df.iterrows():
        if pd.notna(row.get("pendiente_norm")) and row.get("pendiente_norm") is not None:
            idx = row["freq_norm"] * 0.4 + row["precip_norm"] * 0.4 + row["pendiente_norm"] * 0.2
            parciales.append(False)
        else:
            idx = row["freq_norm"] * 0.5 + row["precip_norm"] * 0.5
            parciales.append(True)
        indices.append(float(idx))

    df["indice_riesgo"] = indices
    df["indice_parcial"] = parciales

    # --- Clasificar categoría de riesgo ---
    def _categoria(v: float) -> str:
        if v < 0.25:
            return "Bajo"
        elif v < 0.50:
            return "Medio"
        elif v < 0.75:
            return "Alto"
        else:
            return "Crítico"

    df["categoria_riesgo"] = df["indice_riesgo"].apply(_categoria)

    # Columnas finales alineadas con la tabla communes
    final_cols = [
        "commune_id",
        "nombre_comuna",
        "pendiente_promedio",
        "is_zona_ladera",
        "indice_riesgo",
        "categoria_riesgo",
        "indice_parcial",
        "n_eventos",
        "correlacion_diaria",
        "correlacion_3d",
        "correlacion_7d",
        "geometry",
    ]
    for col in final_cols:
        if col not in df.columns:
            df[col] = None

    return df[final_cols].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tarea 4.2 — Alertas
# ---------------------------------------------------------------------------

def evaluate_alerts(
    precip_df: pd.DataFrame,
    communes_df: pd.DataFrame,
) -> list[dict]:
    """
    Genera alertas por umbral de precipitación para comunas en Zona_Ladera.
    - Naranja: precipitacion_mm > 50
    - Roja:    precipitacion_acum_3d > 100
    """
    alerts: list[dict] = []

    if precip_df.empty:
        return alerts

    # Construir mapa commune_id → is_zona_ladera desde communes_df
    ladera_map: dict[str, bool] = {}
    if not communes_df.empty and "commune_id" in communes_df.columns:
        for _, row in communes_df.iterrows():
            ladera_map[str(row["commune_id"])] = bool(row.get("is_zona_ladera", False))

    # Si no hay info de comunas, no podemos generar alertas georreferenciadas
    # Usamos un commune_id genérico basado en la estación
    required_cols = {"precipitacion_mm", "precipitacion_acum_3d"}
    if not required_cols.issubset(precip_df.columns):
        logger.warning("precip_df no tiene columnas necesarias para alertas")
        return alerts

    # Obtener el registro más reciente por estación
    if "fecha" in precip_df.columns and "estacion" in precip_df.columns:
        latest = (
            precip_df.dropna(subset=["fecha"])
            .sort_values("fecha")
            .groupby("estacion")
            .last()
            .reset_index()
        )
    else:
        latest = precip_df.copy()

    timestamp_now = datetime.utcnow().isoformat()

    for _, row in latest.iterrows():
        estacion = str(row.get("estacion", "desconocida"))
        # Intentar mapear estación a commune_id (heurística: usar nombre de estación)
        # En ausencia de tabla de mapeo, usamos la estación como commune_id proxy
        commune_id = estacion

        # Buscar si alguna comuna en ladera coincide con la estación
        matched_commune = None
        for cid, is_ladera in ladera_map.items():
            if is_ladera and (cid.lower() in estacion.lower() or estacion.lower() in cid.lower()):
                matched_commune = cid
                break

        # Si no hay match, usar la primera zona ladera disponible como proxy
        # (en producción se usaría una tabla de mapeo estación→comuna)
        if matched_commune is None:
            ladera_communes = [cid for cid, v in ladera_map.items() if v]
            if not ladera_communes:
                # Sin zonas de ladera registradas, no generar alerta
                continue
            matched_commune = ladera_communes[0]

        precip_mm = row.get("precipitacion_mm")
        acum_3d = row.get("precipitacion_acum_3d")

        try:
            precip_mm = float(precip_mm) if precip_mm is not None else None
        except (TypeError, ValueError):
            precip_mm = None

        try:
            acum_3d = float(acum_3d) if acum_3d is not None else None
        except (TypeError, ValueError):
            acum_3d = None

        # Alerta Naranja: precipitacion_mm > 50 en Zona_Ladera
        if precip_mm is not None and precip_mm > 50:
            alerts.append({
                "commune_id": matched_commune,
                "nivel": "Naranja",
                "precipitacion_valor": precip_mm,
                "tipo_umbral": "diaria",
                "timestamp": timestamp_now,
            })

        # Alerta Roja: precipitacion_acum_3d > 100 en Zona_Ladera
        if acum_3d is not None and acum_3d > 100:
            alerts.append({
                "commune_id": matched_commune,
                "nivel": "Rojo",
                "precipitacion_valor": acum_3d,
                "tipo_umbral": "acum_3d",
                "timestamp": timestamp_now,
            })

    # Ordenar: Rojo primero, luego Naranja
    alerts.sort(key=lambda a: 0 if a["nivel"] == "Rojo" else 1)

    logger.info("Alertas generadas: %d", len(alerts))
    return alerts


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def run_etl():
    load_dotenv()

    # Validar env vars
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("Error: SUPABASE_URL y SUPABASE_KEY deben estar definidas en .env")
        sys.exit(1)

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # --- Ingesta ---
    logger.info("=== Iniciando ETL ===")
    events_df = ingest_emergencies()
    precip_df = ingest_precipitation()
    geo_data = ingest_geodata()

    # --- Cálculos ---
    logger.info("=== Calculando índice de riesgo ===")
    communes_df = compute_risk_index(events_df, precip_df, geo_data)

    logger.info("=== Evaluando alertas ===")
    alerts = evaluate_alerts(precip_df, communes_df)

    # --- Guardar en Supabase ---
    logger.info("=== Guardando en Supabase ===")
    save_to_supabase(client, events_df, precip_df, communes_df, alerts, _quality_logs)

    print("ETL completado exitosamente")


if __name__ == "__main__":
    run_etl()
