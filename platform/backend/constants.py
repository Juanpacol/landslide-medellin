"""
Configuración operativa del despliegue.

Las REGLAS DE NEGOCIO puras (umbrales de riesgo, categorías, estado
compuesto Verde/Amarillo/Rojo) viven en `domain/risk_rules.py` — importar
de allí directamente.

Lo que SÍ es de este archivo: configuración operativa (cooldowns de alertas,
intervalos esperados de scrapers) — parámetros de despliegue, no reglas del
dominio.
"""

from __future__ import annotations

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
