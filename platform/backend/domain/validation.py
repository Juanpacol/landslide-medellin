"""Validaciones de dominio, invocadas explícitamente antes de cada `db.add`/commit.

Nada de interceptores globales de SQLAlchemy: el estilo del repo es llamada
explícita (igual que `log_audit_event`, `_get_webhook_url`), no magia oculta.
Puro, sin I/O — testeable sin BD.
"""

from __future__ import annotations

from domain.pii import redact_pii
from errors.error_handler import ValidationError

# Fuente única de verdad para el estado de una corrida de scraper — antes
# duplicado entre api/routes/scraper.py y alerts/slack.py (dos sets idénticos
# mantenidos a mano por separado).
SUCCESS_STATUSES = frozenset({"ok", "completed", "success"})
FAILURE_STATUSES = frozenset({"failed", "error"})
_KNOWN_SCRAPE_STATUSES = SUCCESS_STATUSES | FAILURE_STATUSES | {"started"}

_MIN_REPORT_LENGTH = 10


def validate_scrape_log_status(status: str) -> str:
    """Hoy `status` es un string libre que entra sin validar a `scraping_logs`
    y rompe silenciosamente la clasificación de
    `alerts/slack.py::check_and_fire_scraper_alerts` (un typo nunca se
    detecta como éxito ni como fallo). Lanza ValidationError si no es uno de
    los valores conocidos."""
    if status not in _KNOWN_SCRAPE_STATUSES:
        raise ValidationError(
            f"status '{status}' no reconocido; debe ser uno de: {sorted(_KNOWN_SCRAPE_STATUSES)}"
        )
    return status


def validate_citizen_report(descripcion: str, commune_id: str | None) -> str:
    """Trim + longitud mínima (mismo umbral que hoy en `report_incident`) +
    redacción de PII antes de guardar el reporte del ciudadano. La
    descripción es texto libre y puede contener nombre/dirección/teléfono
    que el ciudadano escriba sin que se le pida — se redacta antes de tocar
    la BD, no después."""
    descripcion = (descripcion or "").strip()
    if len(descripcion) < _MIN_REPORT_LENGTH:
        raise ValidationError(
            "Para registrar el reporte necesito una descripción breve de lo que "
            "observas (por ejemplo: grietas en una pared, movimiento de tierra, "
            "agua turbia bajando por la ladera)."
        )
    return redact_pii(descripcion)


def validate_sensor_reading(
    value: float | None, *, field: str, min_value: float = -50.0, max_value: float = 500.0
) -> float | None:
    """Centraliza el patrón disperso en los scrapers de filtrar sentinelas
    ("sin dato" de SIATA, típicamente <= -900) y valores fuera de rango
    físico razonable. Devuelve None (no lanza) para no cambiar el
    comportamiento tolerante actual de los scrapers — una lectura inválida
    se descarta, no tumba la ingesta de las demás."""
    if value is None:
        return None
    if value <= -900:
        return None
    if not (min_value <= value <= max_value):
        return None
    return value
