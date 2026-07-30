"""
SINGLE source of truth for Medellín's territory (16 comunas + 5
corregimientos).

There used to be 5+ diverging copies (api/routes/risk.py::_COMUNAS_BASE,
api/routes/rain.py::_COMUNAS, alerts/slack.py::_NAMES,
agent/risk_explanations.py::_NOMBRES, agent/tools.py::COMMUNE_LABELS) and TWO
id schemes coexisting with no central mapping:

- **canonical id** ("1".."21"): the one the DATA uses — ml_features,
  risk_predictions, rainfall_timeseries (scrapers map corregimientos to
  17-21 via infrastructure/external/arcgis_client.py).
- **official code** ("01".."16", "50".."90"): Medellín's cartography
  (ArcGIS) and institutional documents.

The divergence caused real bugs: the name dictionaries only had official
codes, so a corregimiento alert with data under id "18" came out as
"Comuna 18" instead of "San Cristóbal", and prediction lookups by official
code ("50") never found anything.

Rule: ALL code speaks canonical id; the official code is only used at the
boundary with ArcGIS/cartography (via `official_code`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CommuneInfo:
    id: str  # canonical id — the one ml_features/risk_predictions use
    official_code: str  # Medellín's official code (cartography/ArcGIS)
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


# ── Centroids (lat, lon) ───────────────────────────────────────────────────────
#
# Extracted ONCE from Medellín's official cartography (layer 11 of
# CartografiaBase, the same one `scraper/medellin_datos.py` queries) via
# `ring_centroid_lonlat` over each polygon's outer ring.
#
# Why they live here and not only in the DB: `ml/seismic_features.py` and
# `alerts/evacuation.py` read them EXCLUSIVELY from
# `ml_features.features["centroid_lat"/"centroid_lon"]`, which only
# `scraper/medellin_datos.py` writes (24h cadence). If that scraper hadn't run
# on a given base, the lookup returned `{}` and all 21 communes fell back to
# the valley's center: the per-commune seismic signal degraded to a CONSTANT,
# silently, with no alert. With these values as a seed that's impossible.
#
# Scraped values ALWAYS take priority over these: they come from the same
# source but may reflect a later cartographic update. This is the floor, not
# the ground truth.
CENTROIDS: dict[str, tuple[float, float]] = {
    "1": (6.291857, -75.542108),
    "2": (6.297073, -75.553417),
    "3": (6.273962, -75.539377),
    "4": (6.283663, -75.558811),
    "5": (6.294420, -75.570015),
    "6": (6.301742, -75.583903),
    "7": (6.282372, -75.599600),
    "8": (6.244203, -75.537911),
    "9": (6.229320, -75.542954),
    "10": (6.244385, -75.564929),
    "11": (6.254970, -75.596937),
    "12": (6.261715, -75.605567),
    "13": (6.257677, -75.619454),
    "14": (6.197583, -75.554248),
    "15": (6.205711, -75.592981),
    "16": (6.218979, -75.608822),
    "17": (6.335893, -75.695376),
    "18": (6.285129, -75.611013),
    "19": (6.224054, -75.614596),
    "20": (6.196107, -75.669300),
    "21": (6.240551, -75.533109),
}

# Approximate center of the Valle de Aburrá. Last resort for an unknown id;
# should NOT be used for any of the 21 communes (there's a test verifying this).
VALLEY_CENTROID: tuple[float, float] = (6.2442, -75.5812)


def centroid(value: str | int | None) -> tuple[float, float] | None:
    """(lat, lon) of a commune's centroid. Accepts canonical id or official code."""
    cid = canonical_id(value)
    if cid is None:
        return None
    return CENTROIDS.get(cid)


def canonical_id(value: str | int | None) -> str | None:
    """Normalizes any id (canonical, official, zero-padded) to canonical.

    "18" → "18" · "60" → "18" · "05" → "5" · "m-7" → "7" · None → None.
    Official corregimiento codes (50-90) are translated; any other number
    just gets its leading zeros stripped.
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
    return normalized  # unknown id: returned normalized, not None


def display_name(value: str | int | None) -> str:
    """Name to display. Accepts canonical id or official code."""
    cid = canonical_id(value)
    if cid and cid in BY_ID:
        return BY_ID[cid].nombre
    return f"Comuna {value}" if value is not None else "Sin datos"


# ── Resolution by name (for chat: "¿cómo está el Poblado?") ──────────────────


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
    """Name, alias, canonical id, or official code → canonical id."""
    raw = (nombre_o_id or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return canonical_id(raw)
    return _ALIAS_TO_ID.get(_normalize_token(raw))


def find_communes_in_text(text: str) -> list[str]:
    """Unique commune_ids mentioned in the text (approximate order of appearance).

    Lives here and not in agent/tools.py because it needs `_ALIAS_TO_ID`,
    part of the single source of truth for the territory. It was broken for
    exactly that reason: the "PR1 — domain layer" refactor moved the alias
    map to this module and left the function in agent/tools.py referencing a
    name that no longer existed there, so it raised NameError on every call.
    """
    tnorm = _normalize_token(text)
    hits: list[tuple[int, str]] = []
    for alias, cid in sorted(_ALIAS_TO_ID.items(), key=lambda kv: len(kv[0]), reverse=True):
        if len(alias) < 1:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
        m = re.search(pattern, tnorm)
        if m:
            hits.append((m.start(), cid))
    seen: set[str] = set()
    ordered: list[str] = []
    for _, cid in sorted(hits, key=lambda x: x[0]):
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)
    return ordered
