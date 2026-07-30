"""Domain validations, called explicitly before every `db.add`/commit.

No global SQLAlchemy interceptors: the repo's style is explicit calls (same
as `log_audit_event`, `_get_webhook_url`), not hidden magic. Pure, no I/O —
testable without a database.
"""

from __future__ import annotations

from domain.pii import redact_pii
from errors.error_handler import ValidationError

# Single source of truth for a scraper run's status — previously duplicated
# between api/routes/scraper.py and alerts/slack.py (two identical sets
# maintained by hand separately).
SUCCESS_STATUSES = frozenset({"ok", "completed", "success"})
FAILURE_STATUSES = frozenset({"failed", "error"})
_KNOWN_SCRAPE_STATUSES = SUCCESS_STATUSES | FAILURE_STATUSES | {"started"}

_MIN_REPORT_LENGTH = 10


def validate_scrape_log_status(status: str) -> str:
    """Today `status` is a free string that enters `scraping_logs` unvalidated
    and silently breaks the classification in
    `alerts/slack.py::check_and_fire_scraper_alerts` (a typo is never
    detected as either success or failure). Raises ValidationError if it's
    not one of the known values."""
    if status not in _KNOWN_SCRAPE_STATUSES:
        raise ValidationError(
            f"status '{status}' no reconocido; debe ser uno de: {sorted(_KNOWN_SCRAPE_STATUSES)}"
        )
    return status


def validate_citizen_report(descripcion: str, commune_id: str | None) -> str:
    """Trim + minimum length (same threshold as today in `report_incident`) +
    PII redaction before saving the citizen's report. The description is
    free text and may contain a name/address/phone number the citizen wrote
    without being asked for it — redacted before it touches the DB, not
    after."""
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
    """Centralizes the pattern scattered across scrapers of filtering out
    sentinels (SIATA's "no data", typically <= -900) and values outside a
    reasonable physical range. Returns None (doesn't raise) to keep the
    scrapers' current tolerant behavior — an invalid reading is dropped,
    it doesn't take down ingestion of the rest."""
    if value is None:
        return None
    if value <= -900:
        return None
    if not (min_value <= value <= max_value):
        return None
    return value
