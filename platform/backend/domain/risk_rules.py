"""
Reglas de negocio PURAS de la taxonomía de riesgo — sin I/O, sin SQLAlchemy,
sin HTTP. Movidas desde constants.py (que re-exporta por compatibilidad).

Frontera explícita entre predicción y decisión:
- El MODELO produce un score [0,1] → `risk_level_from_score()` lo traduce a
  categoría canónica.
- La CAPA DE ALERTAS decide acción operativa → `compute_alert_state()`
  combina categoría + lluvia + antecedente en VERDE/AMARILLO/ROJO.
El modelo nunca aprende de estas reglas; las reglas nunca predicen.

Convención canónica:
- Las categorías se ALMACENAN en minúscula sin tilde: bajo|medio|alto|critico.
- Para mostrar al usuario se usa display_label() (capitaliza y agrega tilde).
- Toda comparación contra categorías pasa por normalize_category().
"""

from __future__ import annotations

import unicodedata
from typing import Any

# --- Umbrales score → categoría (conservadores) ---
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


# --- Estado compuesto Verde/Amarillo/Rojo (alistamiento/evacuación) ---
# Umbrales conservadores (MVP): porcentaje de lluvia acumulada hoy y de
# índice antecedente respecto al umbral configurado por comuna. Se calibrarán
# cuando existan series históricas de eventos con timestamp preciso.
YELLOW_RAINFALL_PCT = 0.6
YELLOW_ANTECEDENT_PCT = 0.6
RED_RAINFALL_PCT = 1.0
RED_ANTECEDENT_PCT = 0.8

# El índice antecedente (ml/precip_index.py) no tiene umbral configurado por
# comuna como la lluvia diaria (CommuneThreshold) — valor conservador de
# referencia hasta calibrar con eventos históricos reales.
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
    """Combina lluvia de hoy, índice antecedente y categoría del modelo ML en
    un estado operativo de 3 niveles. `rainfall_pct`/`antecedent_pct` son
    fracciones del umbral configurado (1.0 = 100% del umbral)."""
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
