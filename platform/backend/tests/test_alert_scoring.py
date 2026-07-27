"""Tests puros de domain/alert_scoring.py. Sin BD."""

from __future__ import annotations

from domain.alert_scoring import compute_urgency_score, urgency_label


class TestComputeUrgencyScore:
    def test_critico_reciente(self) -> None:
        score = compute_urgency_score(
            risk_category="critico", alert_type="critical_risk", hours_since_last_alert=2.0
        )
        assert score == 90  # 70 (critico) + 20 (critical_risk), sin boost

    def test_boost_por_silencio_largo(self) -> None:
        with_boost = compute_urgency_score(
            risk_category="alto", alert_type="rainfall", hours_since_last_alert=48.0
        )
        without_boost = compute_urgency_score(
            risk_category="alto", alert_type="rainfall", hours_since_last_alert=2.0
        )
        assert with_boost == without_boost + 15

    def test_nunca_alertado_antes_tambien_suma_boost(self) -> None:
        score = compute_urgency_score(
            risk_category="bajo", alert_type="yellow", hours_since_last_alert=None
        )
        assert score == 10 + 5 + 15  # base bajo + modificador yellow + boost

    def test_scraper_escala_con_fallos_consecutivos(self) -> None:
        pocos = compute_urgency_score(
            risk_category=None,
            alert_type="scraper",
            hours_since_last_alert=1.0,
            consecutive_failures=1,
        )
        muchos = compute_urgency_score(
            risk_category=None,
            alert_type="scraper",
            hours_since_last_alert=1.0,
            consecutive_failures=10,
        )
        assert muchos > pocos

    def test_scraper_tiene_tope(self) -> None:
        score = compute_urgency_score(
            risk_category=None,
            alert_type="scraper",
            hours_since_last_alert=1.0,
            consecutive_failures=999,
        )
        assert score <= 40 + 0  # cap interno de la base scraper, sin boost por hours reciente

    def test_clamp_no_supera_100(self) -> None:
        score = compute_urgency_score(
            risk_category="critico", alert_type="critical_risk", hours_since_last_alert=None
        )
        assert score == 100  # 70+20+15=105, clamp a 100

    def test_clamp_no_baja_de_0(self) -> None:
        score = compute_urgency_score(
            risk_category="categoria-desconocida", alert_type="scraper", hours_since_last_alert=1.0
        )
        assert score >= 0

    def test_categoria_case_insensitive(self) -> None:
        a = compute_urgency_score(
            risk_category="Critico", alert_type="yellow", hours_since_last_alert=1.0
        )
        b = compute_urgency_score(
            risk_category="critico", alert_type="yellow", hours_since_last_alert=1.0
        )
        assert a == b


class TestUrgencyLabel:
    def test_umbrales(self) -> None:
        assert urgency_label(100) == "🔴 Crítico"
        assert urgency_label(80) == "🔴 Crítico"
        assert urgency_label(79) == "🟠 Alto"
        assert urgency_label(55) == "🟠 Alto"
        assert urgency_label(54) == "🟡 Medio"
        assert urgency_label(30) == "🟡 Medio"
        assert urgency_label(29) == "🟢 Bajo"
        assert urgency_label(0) == "🟢 Bajo"
