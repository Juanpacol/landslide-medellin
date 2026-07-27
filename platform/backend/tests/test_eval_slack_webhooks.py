"""
Parametrized evaluation tests for Slack webhook payloads.

Validates that webhook payloads have correct JSON structure, required blocks,
and appropriate content for each alert type.

Run with: pytest tests/test_eval_slack_webhooks.py -v
Or use the /eval-prompt skill: /eval-prompt slack_webhooks
"""

import json
from pathlib import Path

import pytest

from tests.eval_runner import (
    TestResult,
    format_report_summary,
    generate_report,
    save_report,
    validate_slack_webhook,
)

CONFIG_FILE = Path(__file__).parent / "eval_config" / "slack_webhooks.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"


def _build_payload(test_case: dict) -> dict:
    """Builds a minimal Slack payload matching each `payload_type` in the
    eval config. Mirrors the shape `alerts/slack.py` actually produces
    closely enough to exercise `validate_slack_webhook()` meaningfully."""
    payload_type = test_case["payload_type"]

    if payload_type == "critical_risk":
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"⚠️ {test_case['risk_category']}"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Riesgo {test_case['risk_category']}* — Acción inmediata requerida",
                    },
                },
                {"type": "divider"},
            ]
        }
        if "explanation_structured" in test_case:
            structured = test_case["explanation_structured"]
            factors_text = "\n".join(f"• {f}" for f in structured.get("factors", []))
            payload["blocks"].append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"📊 *Por qué:*\n{factors_text}"},
                }
            )
        return payload

    if payload_type == "high_risk":
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"⚠️ Riesgo {test_case['risk_category']}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Riesgo {test_case['risk_category']}* — Requiere atención",
                    },
                },
            ]
        }

    if payload_type == "rainfall_threshold":
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🌧️ *Umbral de lluvia superado*\n"
                            f"Acumulado: {test_case['precip_acum']}mm "
                            f"(umbral: {test_case['threshold']}mm)"
                        ),
                    },
                }
            ]
        }

    # Fallback for generic/test payload types — must still have >=1 block.
    return {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Test payload"}}]}


@pytest.fixture
def slack_webhooks_config():
    """Load slack_webhooks test configuration."""
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


class TestSlackWebhookStructure:
    """Unit tests for Slack webhook payload structure."""

    def test_payload_has_blocks(self):
        """Test that critical risk payload has blocks."""
        payload = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "Critical"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "Risk info"}},
            ]
        }

        expected = {"has_blocks": True, "is_valid_json": True}
        assert validate_slack_webhook(payload, expected)

    def test_payload_valid_json(self):
        """Test that payload is valid JSON."""
        payload = {"blocks": [], "text": "Test"}

        expected = {"is_valid_json": True}
        assert validate_slack_webhook(payload, expected)

    def test_payload_must_contain_text(self):
        """Test that payload contains required text."""
        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Lluvia acumulada 200mm"},
                }
            ]
        }

        expected = {
            "is_valid_json": True,
            "has_blocks": True,
            "must_contain_text": ["Lluvia"],
        }
        assert validate_slack_webhook(payload, expected)

    def test_payload_fails_missing_required_text(self):
        """Test that payload fails if required text is missing."""
        payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Some info"}}]}

        expected = {
            "has_blocks": True,
            "must_contain_text": ["Critical"],
        }
        assert not validate_slack_webhook(payload, expected)

    def test_critical_risk_structure(self):
        """Test critical risk payload structure."""
        payload = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Crítico"}},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Riesgo Crítico* — Acción inmediata requerida",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📊 *Por qué:*\n• Lluvia acumulada 200mm\n• 15 eventos recientes",
                    },
                },
            ]
        }

        expected = {
            "has_blocks": True,
            "is_valid_json": True,
            "block_types": ["header", "section", "divider"],
            "must_contain_text": ["Crítico"],
        }
        assert validate_slack_webhook(payload, expected)


def test_slack_webhooks_batch_evaluation(slack_webhooks_config):
    """Run all slack_webhooks tests and generate report."""
    test_cases = slack_webhooks_config["test_cases"]
    results = []

    for test_case in test_cases:
        try:
            payload = _build_payload(test_case)

            # Validate
            is_valid = validate_slack_webhook(payload, test_case["expected"])

            result = TestResult(
                test_id=test_case["id"],
                passed=is_valid,
                expected=test_case["expected"],
                actual=payload,
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
        prompt_module="alerts/slack",
        test_results=results,
        threshold=0.85,
    )

    report_path = save_report(report, RESULTS_DIR)
    print(format_report_summary(report))

    # Assert threshold
    assert report.threshold_passed, (
        f"Slack webhooks accuracy {report.accuracy * 100:.1f}% below threshold {report.threshold * 100:.0f}%"
    )
