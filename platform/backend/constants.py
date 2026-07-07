"""
Configuración operativa + re-exports de compatibilidad.

Las REGLAS DE NEGOCIO puras (umbrales de riesgo, categorías, estado
compuesto Verde/Amarillo/Rojo) viven en `domain/risk_rules.py` — aquí se
re-exportan para no romper los imports existentes (`from constants import
risk_level_from_score`); el código nuevo debe importar de domain directo.

Lo que SÍ es de este archivo: configuración operativa (cooldowns de alertas,
intervalos esperados de scrapers) — parámetros de despliegue, no reglas del
dominio.
"""

from __future__ import annotations

# Re-exports de compatibilidad (código nuevo: importar de domain.risk_rules).
from domain.risk_rules import (  # noqa: F401
    ALERT_CATEGORIES,
    ALERT_STATE_ACTIONS,
    ANTECEDENT_INDEX_THRESHOLD_MM,
    RED_ANTECEDENT_PCT,
    RED_RAINFALL_PCT,
    RISK_ALTO,
    RISK_BAJO,
    RISK_CATEGORIES,
    RISK_CRITICO,
    RISK_MEDIO,
    RISK_THRESHOLD_ALTO,
    RISK_THRESHOLD_CRITICO,
    RISK_THRESHOLD_MEDIO,
    YELLOW_ANTECEDENT_PCT,
    YELLOW_RAINFALL_PCT,
    alert_level,
    compute_alert_state,
    display_label,
    is_alert_category,
    normalize_category,
    risk_level_from_score,
)

# --- Alert cooldowns (segundos) ---
ALERT_COOLDOWN_RAINFALL_HOURS = 6  # Lluvia excede umbral
ALERT_COOLDOWN_CRITICAL_RISK_HOURS = 1  # Riesgo crítico detectado
ALERT_COOLDOWN_SCRAPER_HOURS = 6  # Scraper caído
ALERT_COOLDOWN_YELLOW_HOURS = 4  # Estado Amarillo (alistamiento)

# --- Scrapers: intervalos esperados por fuente (minutos) ---
# Fuente única de verdad: usada por /api/scraper/health (clasificación de estado)
# y por el watchdog de alertas Slack (detección de staleness).
SCRAPER_INTERVALS_MIN: dict[str, int] = {
    "siata": 30,
    "siata_sismos": 30,
    "dagrd": 60,
    "ideam": 360,
    "medellin_datos": 1440,
}
# Una fuente sin éxito hace más de FACTOR × intervalo se considera caída,
# aunque no haya filas de error (p. ej. GitHub Actions deshabilitado = silencio).
SCRAPER_STALE_FACTOR = 3
