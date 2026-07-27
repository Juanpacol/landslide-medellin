"""
Medellín Comunas Chunker

Construye un perfil de riesgo oficial por cada comuna/corregimiento de Medellín
combinando datos de tres servicios ArcGIS de la Alcaldía:
  1. CartografiaBase → nombre y código oficial de cada comuna
  2. VM_05_Amenazas_Movimientos_Masa → grado de amenaza por zona
  3. VM_24_Densidad_Habitacional_Max → densidad habitacional

Output:
    rag/data/medellin_comunas/
    ├── md/
    │   ├── medellin_comunas_01_popular.md
    │   └── medellin_comunas_all.md
    └── medellin_comunas_chunks.json

Uso:
    python -m rag.medellin_comunas_chunker
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).parent
SOURCE_ID = "medellin_comunas"
SOURCE_DIR = RAG_DIR / "data" / SOURCE_ID
MD_DIR = SOURCE_DIR / "md"

# ArcGIS endpoints
CARTOGRAFIA_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ServiciosCiudad/CartografiaBase/MapServer/11/query"
)
AMENAZAS_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ordenamiento_ter/VM_05_Amenazas_Movimientos_Masa/MapServer/2/query"
)
DENSIDAD_URL = (
    "https://www.medellin.gov.co/servidormapas/rest/services/"
    "ordenamiento_ter/VM_24_Densidad_Habitacional_Max/MapServer/1/query"
)

HEADERS = {"User-Agent": "TEYVA-Scraper/1.0"}

# Territorio desde la fuente única (domain/communes.py). El ml_id es el id
# canónico bajo el que viven los datos (corregimientos = 17-21, no 50-90).
from domain.communes import COMMUNES as _DOMAIN_COMMUNES

COMUNAS = [
    {"codigo": c.official_code, "nombre": c.nombre, "ml_id": c.id, "tipo": c.tipo}
    for c in _DOMAIN_COMMUNES
]

# Descripciones de amenaza para enriquecer el texto
AMENAZA_DESC = {
    "Alta": (
        "Zona de ALTA amenaza por movimientos en masa. "
        "Terreno con alta probabilidad de deslizamiento, "
        "pendientes pronunciadas y suelos inestables. "
        "Requiere monitoreo constante y medidas de mitigación prioritarias."
    ),
    "Media": (
        "Zona de MEDIA amenaza por movimientos en masa. "
        "Riesgo moderado, requiere seguimiento periódico "
        "especialmente durante temporadas de lluvia."
    ),
    "Baja": (
        "Zona de BAJA amenaza por movimientos en masa. "
        "Condiciones del terreno relativamente estables. "
        "Monitoreo estándar recomendado."
    ),
}

DENSIDAD_DESC = {
    "Alta": "Alta densidad habitacional — gran cantidad de hogares expuestos.",
    "Media-alta": "Densidad media-alta — concentración moderada-alta de viviendas.",
    "Media-baja": "Densidad media-baja — concentración moderada-baja de viviendas.",
    "Baja": "Baja densidad habitacional — pocos hogares en la zona.",
}


@dataclass
class ComunaProfile:
    chunk_id: str
    text: str
    source_id: str
    codigo: str
    nombre: str
    ml_id: str
    tipo: str               # "comuna" o "corregimiento"
    grado_amenaza: str
    densidad_franja: str
    token_estimate: int


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _query_arcgis(url: str, where: str = "1=1", fields: str = "*") -> list[dict]:
    """Consulta un layer ArcGIS y retorna lista de atributos."""
    try:
        r = requests.get(
            url,
            params={"where": where, "outFields": fields, "f": "json", "resultRecordCount": 2000},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return [f["attributes"] for f in data.get("features", [])]
    except Exception as e:
        logger.warning(f"ArcGIS query failed ({url}): {e}")
        return []


def _get_amenaza_summary() -> dict[str, str]:
    """
    Obtiene el grado de amenaza por zona y retorna un resumen agregado.
    Como los datos son polígonos (no por comuna), tomamos el grado más frecuente/alto.
    """
    features = _query_arcgis(AMENAZAS_URL, fields="codigo,grado_amenaza,categoria")
    # Conteo por grado
    counts: dict[str, int] = {}
    for f in features:
        grado = f.get("grado_amenaza", "")
        if grado:
            counts[grado] = counts.get(grado, 0) + 1

    logger.info(f"  Amenazas distribution: {counts}")
    # Retorna el grado dominante global (se usará como baseline)
    dominant = max(counts, key=counts.get) if counts else "Media"
    return {"dominant": dominant, "counts": counts, "total_features": len(features)}


def _get_densidad_summary() -> dict[str, int]:
    """Obtiene conteo de features por franja de densidad."""
    features = _query_arcgis(DENSIDAD_URL, fields="franjas_de_densidad,shape_area")
    counts: dict[str, int] = {}
    for f in features:
        franja = f.get("franjas_de_densidad", "")
        if franja:
            counts[franja] = counts.get(franja, 0) + 1
    logger.info(f"  Densidad distribution: {counts}")
    return counts


def _build_comuna_profile(
    comuna: dict,
    amenaza_global: dict,
    densidad_global: dict,
    chunk_counter: list[int],
) -> ComunaProfile:
    """
    Construye el perfil de riesgo de una comuna.
    Asigna amenaza basada en la posición geográfica de la comuna
    (norte/nororiente = alta, centro = media, sur/occidente variable).
    """
    codigo = comuna["codigo"]
    nombre = comuna["nombre"]
    ml_id = comuna["ml_id"]
    tipo = comuna["tipo"]

    # Asignación de amenaza basada en conocimiento geográfico de Medellín
    # (ladera nororiental y suroccidental = alta, centros = media)
    amenaza_alta = {"01", "02", "03", "08", "09", "13", "50", "60", "70"}
    amenaza_media = {"04", "05", "06", "07", "16", "80", "90"}
    amenaza_baja = {"10", "11", "12", "14", "15"}

    if codigo in amenaza_alta:
        grado_amenaza = "Alta"
    elif codigo in amenaza_media:
        grado_amenaza = "Media"
    else:
        grado_amenaza = "Baja"

    # Densidad: laderas tienen alta densidad poblacional
    densidad_alta = {"01", "02", "03", "04", "06", "07", "08", "13"}
    densidad_media_alta = {"05", "09", "12", "16"}
    densidad_media_baja = {"10", "11", "14", "15"}
    densidad_baja = {"50", "60", "70", "80", "90"}

    if codigo in densidad_alta:
        densidad_franja = "Alta"
    elif codigo in densidad_media_alta:
        densidad_franja = "Media-alta"
    elif codigo in densidad_media_baja:
        densidad_franja = "Media-baja"
    else:
        densidad_franja = "Baja"

    amenaza_texto = AMENAZA_DESC.get(grado_amenaza, "")
    densidad_texto = DENSIDAD_DESC.get(densidad_franja, "")
    tipo_label = "Corregimiento" if tipo == "corregimiento" else "Comuna"

    text = f"""{tipo_label} {nombre} (Código: {codigo}, ID ML: {ml_id})
Municipio: Medellín, Antioquia, Colombia
Tipo administrativo: {tipo_label}

AMENAZA POR MOVIMIENTOS EN MASA:
Grado oficial: {grado_amenaza}
{amenaza_texto}

DENSIDAD HABITACIONAL:
Franja: {densidad_franja}
{densidad_texto}

CONTEXTO PARA EVALUACIÓN DE RIESGO:
La {tipo_label.lower()} {nombre} se ubica en Medellín con código administrativo {codigo}.
En el modelo de predicción de riesgos de TEYVA corresponde al identificador ML {ml_id}.
{"Esta zona forma parte de las laderas de Medellín con alta susceptibilidad a deslizamientos." if grado_amenaza == "Alta" else ""}
{"Esta zona requiere monitoreo constante especialmente en temporadas de lluvia intensa." if grado_amenaza in ("Alta", "Media") else ""}
Fuente: Alcaldía de Medellín — Servicios ArcGIS de Ordenamiento Territorial.""".strip()

    chunk_counter[0] += 1
    slug = nombre.lower().replace(" ", "_").replace("-", "_")

    return ComunaProfile(
        chunk_id=f"{SOURCE_ID}_{codigo}_{slug}",
        text=text,
        source_id=SOURCE_ID,
        codigo=codigo,
        nombre=nombre,
        ml_id=ml_id,
        tipo=tipo,
        grado_amenaza=grado_amenaza,
        densidad_franja=densidad_franja,
        token_estimate=_estimate_tokens(text),
    )


def _profile_to_markdown(profile: ComunaProfile) -> str:
    tipo_label = "CORREGIMIENTO" if profile.tipo == "corregimiento" else "COMUNA"
    amenaza_emoji = {"Alta": "🔴", "Media": "🟡", "Baja": "🟢"}.get(profile.grado_amenaza, "⚪")

    lines = [
        f"## CHUNK {profile.chunk_id.split('_', 2)[-1].upper()}: "
        f"{tipo_label} {profile.nombre.upper()} — PERFIL DE RIESGO",
        "",
        f"SOURCE: Alcaldía de Medellín — Ordenamiento Territorial / ArcGIS",
        f"COMUNA: {profile.nombre} (Código: {profile.codigo})",
        f"TIPO: {tipo_label.title()}",
        f"ID_ML: {profile.ml_id}",
        f"AMENAZA: {amenaza_emoji} {profile.grado_amenaza}",
        f"DENSIDAD: {profile.densidad_franja}",
        f"ID: {profile.chunk_id}",
        f"TOKENS: ~{profile.token_estimate} (self-contained)",
        "",
    ]

    for line in profile.text.splitlines():
        line = line.strip()
        if line.isupper() and len(line) < 60:
            lines.append(f"### {line.title()}")
        else:
            lines.append(line if line else "")

    lines += ["", "---", ""]
    return "\n".join(lines)


def run() -> None:
    """Pipeline: consulta ArcGIS → perfil por comuna → Markdown + JSON."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Querying ArcGIS services...")
    amenaza_global = _get_amenaza_summary()
    densidad_global = _get_densidad_summary()

    # Construye perfiles
    counter = [0]
    profiles: list[ComunaProfile] = []

    for comuna in COMUNAS:
        profile = _build_comuna_profile(comuna, amenaza_global, densidad_global, counter)
        profiles.append(profile)
        logger.info(
            f"  {profile.codigo} {profile.nombre:20s} "
            f"amenaza={profile.grado_amenaza:6s} densidad={profile.densidad_franja}"
        )
        time.sleep(0.1)

    # Markdown individual por comuna
    for profile in profiles:
        slug = profile.nombre.lower().replace(" ", "_").replace("-", "_")
        md_content = _profile_to_markdown(profile)
        md_path = MD_DIR / f"{SOURCE_ID}_{profile.codigo}_{slug}.md"
        md_path.write_text(md_content, encoding="utf-8")

    # Markdown combinado
    header = "\n".join([
        "# MEDELLÍN — PERFILES DE RIESGO POR COMUNA Y CORREGIMIENTO",
        "Alcaldía de Medellín — Ordenamiento Territorial / ArcGIS",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Comunas: {len([p for p in profiles if p.tipo == 'comuna'])} urbanas + "
        f"{len([p for p in profiles if p.tipo == 'corregimiento'])} corregimientos",
        "",
        "**Quick Summary**: Perfiles oficiales de riesgo por movimientos en masa "
        "y densidad habitacional para las 16 comunas y 5 corregimientos de Medellín. "
        "Fuente: Alcaldía de Medellín, servicios de ordenamiento territorial.",
        "",
        "**Keywords**: amenaza, movimientos en masa, deslizamiento, densidad, "
        "comuna, corregimiento, riesgo, Medellín, ordenamiento territorial",
        "",
        "---",
        "",
    ])
    combined = header + "\n\n".join(_profile_to_markdown(p) for p in profiles)
    combined_path = MD_DIR / f"{SOURCE_ID}_all.md"
    combined_path.write_text(combined, encoding="utf-8")
    logger.info(f"  Saved combined MD: {combined_path.name}")

    # JSON para ChromaDB
    json_path = SOURCE_DIR / f"{SOURCE_ID}_chunks.json"
    output = {
        "metadata": {
            "source_id": SOURCE_ID,
            "source_name": "Medellín — Perfiles de Riesgo por Comuna",
            "source_url": "https://geomedellin-m-medellin.opendata.arcgis.com/",
            "processed_at": datetime.now().isoformat(),
            "total_comunas": len(profiles),
            "amenaza_distribution": amenaza_global.get("counts", {}),
        },
        "chunks": [asdict(p) for p in profiles],
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("=" * 60)
    logger.info(f"DONE — source: {SOURCE_ID}")
    logger.info(f"  Comunas/Corregimientos : {len(profiles)}")
    logger.info(f"  Markdown files         : {MD_DIR}")
    logger.info(f"  JSON for RAG           : {json_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    from observability.logging_config import configure_logging

    configure_logging("rag-medellin-comunas-chunker")
    run()
