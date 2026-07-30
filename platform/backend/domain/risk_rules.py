"""
PURE business rules for the risk taxonomy — no I/O, no SQLAlchemy, no HTTP.
Moved from constants.py (which re-exports for compatibility).

Explicit boundary between prediction and decision:
- The MODEL produces a [0,1] score → `risk_level_from_score()` translates it
  into a canonical category.
- The ALERT LAYER decides operational action → `compute_alert_state()`
  combines category + rain + antecedent into GREEN/YELLOW/RED.
The model never learns from these rules; the rules never predict. As of
`specs/003-inference-engine/`, this boundary is what
`application/neurosymbolic/infer.py` closes: the rules DO now feed back into
the final level via declared conflict-resolution precedence
(`docs/adr/0003-conflict-resolution-precedence.md`) — this module still only
defines the taxonomy and thresholds, not the combination logic.

Canonical convention:
- Categories are STORED lowercase, no accents: bajo|medio|alto|critico.
- Use display_label() to show the user (capitalizes and adds the accent).
- Every comparison against a category goes through normalize_category().
"""

from __future__ import annotations

import unicodedata
from typing import Any

# --- Score → category thresholds (conservative) ---
# A score >= the threshold moves up a level. Generated with SMOTE; conservative
# to avoid over-alerting after retrains.
RISK_THRESHOLD_MEDIO = 0.35
RISK_THRESHOLD_ALTO = 0.65
RISK_THRESHOLD_CRITICO = 0.90

# --- Canonical labels (stored in DB: lowercase, no accents) ---
RISK_BAJO = "bajo"
RISK_MEDIO = "medio"
RISK_ALTO = "alto"
RISK_CRITICO = "critico"

RISK_CATEGORIES: tuple[str, ...] = (RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO)

# Categories that trigger an operational alert.
ALERT_CATEGORIES: frozenset[str] = frozenset({RISK_ALTO, RISK_CRITICO})

# User-facing labels (presentation) — Spanish, stakeholders are Spanish-speaking.
_DISPLAY_LABELS: dict[str, str] = {
    RISK_BAJO: "Bajo",
    RISK_MEDIO: "Medio",
    RISK_ALTO: "Alto",
    RISK_CRITICO: "Crítico",
}

# Alert level (color) per category — Spanish, shown to Gestión del Riesgo.
_ALERT_LEVEL: dict[str, str] = {
    RISK_CRITICO: "Rojo",
    RISK_ALTO: "Naranja",
}


def risk_level_from_score(score: float | None) -> str:
    """Converts a [0,1] score into a canonical category (lowercase, no accent)."""
    if score is None:
        return RISK_BAJO
    s = float(score)
    if s < RISK_THRESHOLD_MEDIO:
        return RISK_BAJO
    if s < RISK_THRESHOLD_ALTO:
        return RISK_MEDIO
    if s < RISK_THRESHOLD_CRITICO:
        return RISK_ALTO
    return RISK_CRITICO


def normalize_category(value: Any) -> str:
    """Normalizes any category string (legacy/uppercase/accented) to canonical form.

    "Crítico" -> "critico", "ALTO" -> "alto", "  Medio " -> "medio".
    """
    if value is None:
        return ""
    s = str(value).strip().lower()
    # Strip accents (NFD + drop combining marks).
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def is_alert_category(value: Any) -> bool:
    """True if the category (in any format) is alto or critico."""
    return normalize_category(value) in ALERT_CATEGORIES


def display_label(value: Any) -> str:
    """User-facing label. Returns 'Sin datos' if unrecognized."""
    return _DISPLAY_LABELS.get(normalize_category(value), "Sin datos")


def alert_level(value: Any) -> str | None:
    """Alert level (Rojo/Naranja) or None if the category isn't an alert category."""
    return _ALERT_LEVEL.get(normalize_category(value))


# --- Composite Green/Yellow/Red state (readiness/evacuation) ---
# Conservative thresholds (MVP): percentage of today's accumulated rain and of
# the antecedent index relative to the commune's configured threshold. To be
# calibrated once precisely-timestamped historical event series exist.
YELLOW_RAINFALL_PCT = 0.6
YELLOW_ANTECEDENT_PCT = 0.6
RED_RAINFALL_PCT = 1.0
RED_ANTECEDENT_PCT = 0.8

# The antecedent index (ml/precip_index.py) has no per-commune configured
# threshold like daily rain does (CommuneThreshold) — conservative reference
# value until calibrated against real historical events.
ANTECEDENT_INDEX_THRESHOLD_MM = 100.0

ALERT_STATE_ACTIONS: dict[str, str] = {
    "ROJO": "Evacuación inmediata hacia zona segura",
    "AMARILLO": "Alistamiento: verificar rutas de evacuación y kit de emergencia",
    "VERDE": "Monitoreo rutinario",
}


def compute_alert_state(
    rainfall_pct: float,
    antecedent_pct: float,
    risk_category: Any,
) -> dict[str, str]:
    """Combines today's rain, the antecedent index and the ML model's category
    into a 3-level operational state. `rainfall_pct`/`antecedent_pct` are
    fractions of the configured threshold (1.0 = 100% of the threshold)."""
    category = normalize_category(risk_category)
    if category == RISK_CRITICO or (
        rainfall_pct >= RED_RAINFALL_PCT and antecedent_pct >= RED_ANTECEDENT_PCT
    ):
        state = "ROJO"
    elif (
        category == RISK_ALTO
        or rainfall_pct >= YELLOW_RAINFALL_PCT
        or antecedent_pct >= YELLOW_ANTECEDENT_PCT
    ):
        state = "AMARILLO"
    else:
        state = "VERDE"
    return {"state": state, "action": ALERT_STATE_ACTIONS[state]}
