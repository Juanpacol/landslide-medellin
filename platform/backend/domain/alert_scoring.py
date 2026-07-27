"""Scoring de urgencia 0-100 para alertas de Slack. Puro, sin I/O.

Explicable, no un número mágico: base por categoría de riesgo + modificador
por tipo de alerta + boost si hace rato no se avisa nada de esto.
"""

from __future__ import annotations

_BASE_BY_CATEGORY: dict[str, int] = {"critico": 70, "alto": 50, "medio": 25, "bajo": 10}
_TYPE_MODIFIER: dict[str, int] = {"critical_risk": 20, "rainfall": 10, "yellow": 5, "scraper": 0}

_STALE_HOURS_THRESHOLD = 24.0
_STALE_BOOST = 15
_SCRAPER_BASE_PER_FAILURE = 10
_SCRAPER_BASE_FLOOR = 15
_SCRAPER_BASE_CAP = 40


def compute_urgency_score(
    *,
    risk_category: str | None,
    alert_type: str,
    hours_since_last_alert: float | None,
    consecutive_failures: int = 0,
) -> int:
    """0-100. `alert_type` ∈ {critical_risk, rainfall, yellow, scraper}.

    Para "scraper" no hay `risk_category` (no es una alerta de riesgo de
    deslizamiento): la base depende de cuántos fallos consecutivos lleva.
    Para el resto: base de la categoría de riesgo + modificador del tipo.

    `hours_since_last_alert` None o >24h suma un boost: "hace rato no se
    avisa nada de esto" es en sí mismo más urgente que un recordatorio
    reciente — señal de que el problema lleva desatendido.
    """
    if alert_type == "scraper":
        score = min(
            _SCRAPER_BASE_FLOOR + consecutive_failures * _SCRAPER_BASE_PER_FAILURE,
            _SCRAPER_BASE_CAP,
        )
    else:
        category = (risk_category or "").strip().lower()
        score = _BASE_BY_CATEGORY.get(category, 10) + _TYPE_MODIFIER.get(alert_type, 0)

    if hours_since_last_alert is None or hours_since_last_alert > _STALE_HOURS_THRESHOLD:
        score += _STALE_BOOST

    return max(0, min(100, score))


def urgency_label(score: int) -> str:
    if score >= 80:
        return "🔴 Crítico"
    if score >= 55:
        return "🟠 Alto"
    if score >= 30:
        return "🟡 Medio"
    return "🟢 Bajo"
