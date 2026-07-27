"""
Graded evaluation for Slack webhook payloads — adds a 1-10 Ollama-judge
quality score on top of the binary structure validation in
test_eval_slack_webhooks.py.

Requires Ollama running (skips otherwise).

Run with: pytest tests/test_eval_slack_webhooks_graded.py -v -s
Or use the /eval-prompt skill: /eval-prompt slack_webhooks --grading
"""

import json
from pathlib import Path

import httpx
import pytest

from tests.eval_grader import grade_slack_webhook
from tests.eval_runner import (
    GradedTestResult,
    find_latest_report,
    format_graded_report_summary,
    generate_report,
    load_report_dict,
    save_report,
    validate_slack_webhook,
)
from tests.test_eval_slack_webhooks import _build_payload

CONFIG_FILE = Path(__file__).parent / "eval_config" / "slack_webhooks.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"
QUALITY_THRESHOLD = 6.5


@pytest.fixture
def slack_webhooks_config():
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


@pytest.mark.asyncio
async def test_slack_webhooks_graded_evaluation(require_ollama, slack_webhooks_config):
    """Runs all slack_webhooks test cases, grading each payload 1-10 via Ollama."""
    test_cases = slack_webhooks_config["test_cases"]

    previous_path = find_latest_report(RESULTS_DIR, "alerts/slack_graded")
    previous_report = load_report_dict(previous_path) if previous_path else None

    results: list[GradedTestResult] = []

    for test_case in test_cases:
        try:
            payload = _build_payload(test_case)
            is_valid = validate_slack_webhook(payload, test_case["expected"])
            risk_category = test_case.get("risk_category", "N/A")
            graded = await grade_slack_webhook(payload, risk_category)

            results.append(
                GradedTestResult(
                    test_id=test_case["id"],
                    passed=is_valid,
                    expected=test_case["expected"],
                    actual=payload,
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
        prompt_module="alerts/slack_graded",
        test_results=results,
        threshold=0.85,
        quality_threshold=QUALITY_THRESHOLD,
    )

    save_report(report, RESULTS_DIR)
    print(format_graded_report_summary(report, previous_report))

    assert report.threshold_passed, (
        f"Slack webhooks accuracy {report.accuracy * 100:.1f}% below threshold {report.threshold * 100:.0f}%"
    )
    if report.average_score is not None:
        assert report.average_score >= QUALITY_THRESHOLD, (
            f"Slack webhooks quality score {report.average_score:.1f}/10 below threshold {QUALITY_THRESHOLD}/10"
        )
