"""Tests puros de los constructores de payload de alerts/slack.py.

Son funciones puras (arman dicts, sin I/O) — se testean directo, sin BD.
"""

from __future__ import annotations

import json

from alerts.slack import (
    _build_critical_risk_payload,
    _build_scraper_alert_payload,
    _build_slack_payload,
    _build_yellow_alert_payload,
)


def _flatten_text(payload: dict) -> str:
    """Concatena todo el texto plano de blocks/attachments para buscar substrings."""
    return json.dumps(payload, ensure_ascii=False)


class TestRainfallPayload:
    def test_incluye_urgencia_y_boton_dashboard(self) -> None:
        payload = _build_slack_payload(
            "1",
            "Popular",
            45.0,
            35.0,
            0.7,
            "alto",
            urgency_score=65,
        )
        text = _flatten_text(payload)
        assert "65/100" in text
        assert "Abrir dashboard" in text


class TestYellowPayload:
    def test_incluye_urgencia_y_boton_dashboard(self) -> None:
        payload = _build_yellow_alert_payload(
            "1",
            "Popular",
            {
                "rainfall_pct": 0.5,
                "antecedent_pct": 0.3,
                "risk_category": "medio",
                "action": "vigilar",
            },
            urgency_score=40,
        )
        text = _flatten_text(payload)
        assert "40/100" in text
        assert "Abrir dashboard" in text


class TestScraperPayload:
    def test_incluye_urgencia_y_boton_dashboard(self) -> None:
        payload = _build_scraper_alert_payload(
            [("siata", "3 fallos consecutivos")],
            urgency_score=35,
        )
        text = _flatten_text(payload)
        assert "35/100" in text
        assert "Abrir dashboard" in text


class TestCriticalRiskPayload:
    def test_incluye_urgencia(self) -> None:
        payload = _build_critical_risk_payload(
            "1",
            "Popular",
            0.95,
            "crítico",
            "explicación",
            "recomendación",
            "▁▂▃",
            [10.0, 20.0],
            urgency_score=95,
        )
        text = _flatten_text(payload)
        assert "95/100" in text

    def test_ya_tenia_botones_de_enlace_y_los_conserva(self) -> None:
        payload = _build_critical_risk_payload(
            "1",
            "Popular",
            0.95,
            "crítico",
            "explicación",
            "recomendación",
            "▁▂▃",
            [10.0, 20.0],
            urgency_score=95,
        )
        text = _flatten_text(payload)
        assert "Ver gráfica" in text
        assert "Abrir dashboard" in text
