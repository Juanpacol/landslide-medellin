"""
Fuente ÚNICA de verdad para el territorio de Medellín (16 comunas + 5
corregimientos).

Antes existían 5+ copias divergentes (api/routes/risk.py::_COMUNAS_BASE,
api/routes/rain.py::_COMUNAS, alerts/slack.py::_NAMES,
agent/risk_explanations.py::_NOMBRES, agent/tools.py::COMMUNE_LABELS) y DOS
esquemas de id conviviendo sin mapeo central:

- **id canónico** ("1".."21"): el que usan los DATOS — ml_features,
  risk_predictions, rainfall_timeseries (los scrapers mapean corregimientos
  a 17-21 vía scraper/commune.py::_CORREG_TO_ML).
- **código oficial** ("01".."16", "50".."90"): el de la cartografía de
  Medellín (ArcGIS) y documentos institucionales.

La divergencia causaba bugs reales: los diccionarios de nombres solo tenían
códigos oficiales, así que una alerta del corregimiento con datos bajo id
"18" salía como "Comuna 18" en vez de "San Cristóbal", y los lookups de
predicción por código oficial ("50") no encontraban nada nunca.

Regla: TODO el código habla en id canónico; el código oficial solo se usa
en el borde con ArcGIS/cartografía (vía `official_code`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CommuneInfo:
    id: str  # id canónico — el de ml_features/risk_predictions
    official_code: str  # código oficial de Medellín (cartografía/ArcGIS)
    nombre: str
    tipo: str  # "comuna" | "corregimiento"
    is_ladera: bool


COMMUNES: tuple[CommuneInfo, ...] = (
    CommuneInfo("1", "01", "Popular", "comuna", True),
    CommuneInfo("2", "02", "Santa Cruz", "comuna", True),
    CommuneInfo("3", "03", "Manrique", "comuna", True),
    CommuneInfo("4", "04", "Aranjuez", "comuna", False),
    CommuneInfo("5", "05", "Castilla", "comuna", False),
    CommuneInfo("6", "06", "Doce de Octubre", "comuna", True),
    CommuneInfo("7", "07", "Robledo", "comuna", True),
    CommuneInfo("8", "08", "Villa Hermosa", "comuna", True),
    CommuneInfo("9", "09", "Buenos Aires", "comuna", True),
    CommuneInfo("10", "10", "La Candelaria", "comuna", False),
    CommuneInfo("11", "11", "Laureles-Estadio", "comuna", False),
    CommuneInfo("12", "12", "La América", "comuna", False),
    CommuneInfo("13", "13", "San Javier", "comuna", True),
    CommuneInfo("14", "14", "El Poblado", "comuna", False),
    CommuneInfo("15", "15", "Guayabal", "comuna", False),
    CommuneInfo("16", "16", "Belén", "comuna", True),
    CommuneInfo("17", "50", "Palmitas", "corregimiento", True),
    CommuneInfo("18", "60", "San Cristóbal", "corregimiento", True),
    CommuneInfo("19", "70", "Altavista", "corregimiento", True),
    CommuneInfo("20", "80", "San Antonio de Prado", "corregimiento", True),
    CommuneInfo("21", "90", "Santa Elena", "corregimiento", True),
)

BY_ID: dict[str, CommuneInfo] = {c.id: c for c in COMMUNES}
BY_OFFICIAL_CODE: dict[str, CommuneInfo] = {c.official_code: c for c in COMMUNES}


def canonical_id(value: str | int | None) -> str | None:
    """Normaliza cualquier id (canónico, oficial, con ceros) al canónico.

    "18" → "18" · "60" → "18" · "05" → "5" · "m-7" → "7" · None → None.
    Los códigos oficiales de corregimiento (50-90) se traducen; cualquier
    otro número se limpia de ceros a la izquierda.
    """
    if value is None:
        return None
    s = str(value).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    normalized = str(int(digits))
    padded = digits.zfill(2)
    if normalized in BY_ID:
        return normalized
    if padded in BY_OFFICIAL_CODE:
        return BY_OFFICIAL_CODE[padded].id
    return normalized  # id desconocido: se devuelve normalizado, no None


def display_name(value: str | int | None) -> str:
    """Nombre para mostrar. Acepta id canónico o código oficial."""
    cid = canonical_id(value)
    if cid and cid in BY_ID:
        return BY_ID[cid].nombre
    return f"Comuna {value}" if value is not None else "Sin datos"


# ── Resolución por nombre (para el chat: "¿cómo está el Poblado?") ────────────

def _normalize_token(s: str) -> str:
    s = s.strip().lower()
    nkfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


_ALIAS_TO_ID: dict[str, str] = {}
for _c in COMMUNES:
    _ALIAS_TO_ID[_normalize_token(_c.nombre)] = _c.id

_ALIASES_EXTRA = {
    "doce de octubre": "6",
    "la america": "12",
    "laureles estadio": "11",
    "laureles-estadio": "11",
    "laureles": "11",
    "san cristobal": "18",
    "poblado": "14",
    "candelaria": "10",
    "centro": "10",
    "villa hermosa": "8",
    "belen": "16",
}
for _k, _v in _ALIASES_EXTRA.items():
    _ALIAS_TO_ID.setdefault(_normalize_token(_k), _v)


def resolve_commune_id(nombre_o_id: str) -> str | None:
    """Nombre, alias, id canónico o código oficial → id canónico."""
    raw = (nombre_o_id or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return canonical_id(raw)
    return _ALIAS_TO_ID.get(_normalize_token(raw))
