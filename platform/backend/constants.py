"""
Fuente única de verdad para la taxonomía de riesgo de TEYVA.

Antes existían 3 mapeos de umbral→categoría distintos (ml/predict.py,
api/routes/risk.py, agent/chat.py) con valores y formatos de string
inconsistentes. Eso rompía silenciosamente /api/risk/alerts (filtraba
contra "Alto"/"Crítico" capitalizados mientras la BD guarda "alto"/"critico").

Convención canónica:
- Las categorías se ALMACENAN en minúscula sin tilde: bajo|medio|alto|critico.
- Para mostrar al usuario se usa display_label() (capitaliza y agrega tilde).
- Toda comparación contra categorías pasa por normalize_category().
"""

from __future__ import annotations

import unicodedata
from typing import Any

# --- Umbrales score → categoría (conservadores, alineados a ml/predict.py) ---
# Un score >= al umbral sube de nivel. Generados con SMOTE; conservadores para
# no sobre-alertar tras reentrenos.
RISK_THRESHOLD_MEDIO = 0.35
RISK_THRESHOLD_ALTO = 0.65
RISK_THRESHOLD_CRITICO = 0.90

# --- Etiquetas canónicas (lo que se guarda en BD: minúscula, sin tilde) ---
RISK_BAJO = "bajo"
RISK_MEDIO = "medio"
RISK_ALTO = "alto"
RISK_CRITICO = "critico"

RISK_CATEGORIES: tuple[str, ...] = (RISK_BAJO, RISK_MEDIO, RISK_ALTO, RISK_CRITICO)

# Categorías que disparan alerta operativa.
ALERT_CATEGORIES: frozenset[str] = frozenset({RISK_ALTO, RISK_CRITICO})

# Etiquetas para mostrar al usuario (presentación).
_DISPLAY_LABELS: dict[str, str] = {
    RISK_BAJO: "Bajo",
    RISK_MEDIO: "Medio",
    RISK_ALTO: "Alto",
    RISK_CRITICO: "Crítico",
}

# Nivel de alerta (color) por categoría.
_ALERT_LEVEL: dict[str, str] = {
    RISK_CRITICO: "Rojo",
    RISK_ALTO: "Naranja",
}

# --- Alert cooldowns (segundos) ---
ALERT_COOLDOWN_RAINFALL_HOURS = 6  # Lluvia excede umbral
ALERT_COOLDOWN_CRITICAL_RISK_HOURS = 1  # Riesgo crítico detectado
ALERT_COOLDOWN_SCRAPER_HOURS = 6  # Scraper caído


def risk_level_from_score(score: float | None) -> str:
    """Convierte un score [0,1] en categoría canónica (minúscula sin tilde)."""
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
    """Normaliza cualquier string de categoría (legacy/mayúsculas/tildes) a canónico.

    "Crítico" -> "critico", "ALTO" -> "alto", "  Medio " -> "medio".
    """
    if value is None:
        return ""
    s = str(value).strip().lower()
    # Quita tildes (NFD + descarta marcas combinantes).
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def is_alert_category(value: Any) -> bool:
    """True si la categoría (en cualquier formato) es alto o crítico."""
    return normalize_category(value) in ALERT_CATEGORIES


def display_label(value: Any) -> str:
    """Etiqueta para mostrar al usuario. Devuelve 'Sin datos' si no reconoce."""
    return _DISPLAY_LABELS.get(normalize_category(value), "Sin datos")


def alert_level(value: Any) -> str | None:
    """Nivel de alerta (Rojo/Naranja) o None si la categoría no es de alerta."""
    return _ALERT_LEVEL.get(normalize_category(value))
