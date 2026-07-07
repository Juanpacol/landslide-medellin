"""
Parametrized evaluation tests for risk_explanations prompt.

Validates that risk explanations have correct structure, content, and urgency
for each risk category (bajo, medio, alto, critico).

Run with: pytest tests/test_eval_risk_explanations.py -v
Or use the /eval-prompt skill: /eval-prompt risk_explanations
"""

import json
from pathlib import Path

import pytest

from agent.risk_explanations import (
    _template_explanation_structured,
    _render_narrative,
)
from domain.risk_rules import RISK_THRESHOLD_ALTO, RISK_THRESHOLD_CRITICO, RISK_THRESHOLD_MEDIO
from tests.eval_runner import (
    TestResult,
    format_report_summary,
    generate_report,
    save_report,
    validate_risk_explanation,
)

CONFIG_FILE = Path(__file__).parent / "eval_config" / "risk_explanations.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"


@pytest.fixture
def risk_explanations_config():
    """Load risk_explanations test configuration."""
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def categorize_risk_score(score: float) -> str:
    """Determine risk category from score."""
    if score < RISK_THRESHOLD_MEDIO:
        return "bajo"
    elif score < RISK_THRESHOLD_ALTO:
        return "medio"
    elif score < RISK_THRESHOLD_CRITICO:
        return "alto"
    else:
        return "critico"


def _build_structured(test_case: dict) -> dict:
    """Builds a structured explanation dict for a test case via the real
    `_template_explanation_structured()` signature (commune_id, nombre,
    risk_score, risk_category, precip_acum_mm, threshold_mm, n_events_7d,
    is_ladera)."""
    return _template_explanation_structured(
        commune_id=test_case["commune_id"],
        nombre=test_case["nombre"],
        risk_score=test_case["risk_score"],
        risk_category=test_case["category"],
        precip_acum_mm=test_case["precip_7d"],
        threshold_mm=test_case["threshold_mm"],
        n_events_7d=test_case["n_events"],
        is_ladera=True,
    )


class TestRiskExplanationsStructure:
    """Unit tests for explanation structure (no LLM, no DB)."""

    def test_template_bajo(self):
        """Test template explanation for bajo category."""
        explanation = _template_explanation_structured(
            commune_id="1",
            nombre="Popular",
            risk_score=0.20,
            risk_category="bajo",
            precip_acum_mm=20.0,
            threshold_mm=35.0,
            n_events_7d=0,
            is_ladera=True,
        )

        assert isinstance(explanation, dict)
        assert "title" in explanation
        assert "factors" in explanation
        assert isinstance(explanation["factors"], list)
        assert len(explanation["factors"]) > 0
        assert explanation["urgency"] == "bajo"
        assert "recommended_action" in explanation

    def test_template_medio(self):
        """Test template explanation for medio category."""
        explanation = _template_explanation_structured(
            commune_id="3",
            nombre="Manrique",
            risk_score=0.50,
            risk_category="medio",
            precip_acum_mm=50.0,
            threshold_mm=60.0,
            n_events_7d=3,
            is_ladera=True,
        )

        assert explanation["urgency"] == "medio"
        assert len(explanation["factors"]) > 0

    def test_template_alto(self):
        """Test template explanation for alto category."""
        explanation = _template_explanation_structured(
            commune_id="5",
            nombre="Castilla",
            risk_score=0.75,
            risk_category="alto",
            precip_acum_mm=100.0,
            threshold_mm=70.0,
            n_events_7d=8,
            is_ladera=True,
        )

        assert explanation["urgency"] == "alto"
        assert len(explanation["factors"]) > 0

    def test_template_critico(self):
        """Test template explanation for critico category."""
        explanation = _template_explanation_structured(
            commune_id="7",
            nombre="Robledo",
            risk_score=0.95,
            risk_category="critico",
            precip_acum_mm=200.0,
            threshold_mm=90.0,
            n_events_7d=20,
            is_ladera=True,
        )

        assert explanation["urgency"] == "critico"
        assert len(explanation["factors"]) > 0

    def test_render_narrative_preserves_data(self):
        """Test that narrative rendering preserves structured data."""
        structured = {
            "title": "Riesgo medio por lluvia",
            "factors": ["Lluvia acumulada 50mm", "3 eventos recientes"],
            "urgency": "medio",
            "recommended_action": "Vigilancia activa",
        }

        narrative = _render_narrative(structured)

        assert isinstance(narrative, str)
        assert len(narrative) > 0
        assert "Riesgo medio" in narrative
        assert "Lluvia" in narrative or "lluvia" in narrative.lower()

    def test_template_no_vague_language(self):
        """Test that template avoids vague language."""
        explanation = _template_explanation_structured(
            commune_id="5",
            nombre="Castilla",
            risk_score=0.80,
            risk_category="alto",
            precip_acum_mm=150.0,
            threshold_mm=70.0,
            n_events_7d=10,
            is_ladera=True,
        )

        text = _render_narrative(explanation)
        vague_words = ["podría", "tal vez", "posiblemente", "quizás"]

        for word in vague_words:
            assert word.lower() not in text.lower(), (
                f"Found vague word '{word}' in explanation"
            )

    def test_factors_are_concrete(self):
        """Test that factors contain concrete data, not vague statements."""
        explanation = _template_explanation_structured(
            commune_id="3",
            nombre="Manrique",
            risk_score=0.50,
            risk_category="medio",
            precip_acum_mm=45.0,
            threshold_mm=60.0,
            n_events_7d=2,
            is_ladera=True,
        )

        for factor in explanation["factors"]:
            assert isinstance(factor, str)
            assert len(factor) > 0
            assert len(factor) < 150


def test_risk_explanations_batch_evaluation(risk_explanations_config):
    """Run all risk_explanations tests and generate report."""
    test_cases = risk_explanations_config["test_cases"]
    results = []

    for test_case in test_cases:
        try:
            explanation = _build_structured(test_case)
            explanation["_rendered_text"] = _render_narrative(explanation)

            # Validate
            is_valid = validate_risk_explanation(explanation, test_case["expected"])

            result = TestResult(
                test_id=test_case["id"],
                passed=is_valid,
                expected=test_case["expected"],
                actual=explanation,
                error=None if is_valid else "Validation failed",
            )
        except Exception as exc:
            result = TestResult(
                test_id=test_case["id"],
                passed=False,
                expected=test_case["expected"],
                actual=None,
                error=str(exc),
            )

        results.append(result)

    # Generate and save report
    report = generate_report(
        prompt_module="agent/risk_explanations",
        test_results=results,
        threshold=0.90,
    )

    report_path = save_report(report, RESULTS_DIR)
    print(format_report_summary(report))

    # Assert threshold
    assert (
        report.threshold_passed
    ), f"Risk explanations accuracy {report.accuracy*100:.1f}% below threshold {report.threshold*100:.0f}%"
