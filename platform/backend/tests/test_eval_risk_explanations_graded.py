"""
Graded evaluation for risk_explanations — adds a 1-10 Ollama-judge quality
score on top of the binary structure validation in
test_eval_risk_explanations.py.

Uses the deterministic template path (no ANTHROPIC_API_KEY needed) since
that's what runs in production when the LLM path is unavailable — grading
it tells us whether the *fallback* explanations are good enough on their
own, not just structurally valid.

Requires Ollama running (skips otherwise).

Run with: pytest tests/test_eval_risk_explanations_graded.py -v -s
Or use the /eval-prompt skill: /eval-prompt risk_explanations --grading
"""

import json
from pathlib import Path

import httpx
import pytest

from agent.risk_explanations import _render_narrative, _template_explanation_structured
from tests.eval_grader import grade_risk_explanation
from tests.eval_runner import (
    GradedTestResult,
    find_latest_report,
    format_graded_report_summary,
    generate_report,
    load_report_dict,
    save_report,
    validate_risk_explanation,
)

CONFIG_FILE = Path(__file__).parent / "eval_config" / "risk_explanations.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"
QUALITY_THRESHOLD = 7.0


@pytest.fixture
def risk_explanations_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


@pytest.fixture
def require_ollama():
    """Skip if Ollama isn't running — grading needs a live judge model."""
    import os

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        res = httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
        res.raise_for_status()
    except Exception:
        pytest.skip("Ollama no está corriendo en local (OLLAMA_URL no responde)")


def _build_structured(test_case: dict) -> dict:
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


@pytest.mark.asyncio
async def test_risk_explanations_graded_evaluation(require_ollama, risk_explanations_config):
    """Runs all risk_explanations test cases, grading each 1-10 via Ollama."""
    test_cases = risk_explanations_config["test_cases"]

    previous_path = find_latest_report(RESULTS_DIR, "agent/risk_explanations_graded")
    previous_report = load_report_dict(previous_path) if previous_path else None

    results: list[GradedTestResult] = []

    for test_case in test_cases:
        try:
            structured = _build_structured(test_case)
            narrative = _render_narrative(structured)
            structured["_rendered_text"] = narrative

            is_valid = validate_risk_explanation(structured, test_case["expected"])
            graded = await grade_risk_explanation(
                category=test_case["category"],
                precip=test_case["precip_7d"],
                n_events=test_case["n_events"],
                explanation_text=narrative,
            )

            results.append(
                GradedTestResult(
                    test_id=test_case["id"],
                    passed=is_valid,
                    expected=test_case["expected"],
                    actual=narrative,
                    error=None if is_valid else "Validation failed",
                    score=graded["score"],
                    grader_feedback=graded["feedback"],
                    grader_model=graded.get("grader_model", "ollama"),
                )
            )
        except Exception as exc:
            results.append(
                GradedTestResult(
                    test_id=test_case["id"],
                    passed=False,
                    expected=test_case["expected"],
                    actual=None,
                    error=str(exc),
                    score=None,
                    grader_feedback="",
                )
            )

    report = generate_report(
        prompt_module="agent/risk_explanations_graded",
        test_results=results,
        threshold=0.90,
        quality_threshold=QUALITY_THRESHOLD,
    )

    save_report(report, RESULTS_DIR)
    print(format_graded_report_summary(report, previous_report))

    assert report.threshold_passed, (
        f"Risk explanations accuracy {report.accuracy*100:.1f}% below threshold {report.threshold*100:.0f}%"
    )
    if report.average_score is not None:
        assert report.average_score >= QUALITY_THRESHOLD, (
            f"Risk explanations quality score {report.average_score:.1f}/10 below threshold {QUALITY_THRESHOLD}/10"
        )
