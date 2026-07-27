"""
Evaluation runner — executes test cases against prompts and generates metrics.

This module provides evaluation functions for each critical prompt (chat_rag,
risk_explanations, slack_webhooks). Used by the /eval-prompt skill and tests.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a single test case execution."""

    test_id: str
    passed: bool
    expected: dict
    actual: Any
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class GradedTestResult(TestResult):
    """TestResult extended with a 1-10 LLM-judge score.

    `score` is None when grading failed or was skipped (e.g. Ollama down) —
    callers must treat None as "no data", not as a failing score.
    """

    score: int | None = None
    grader_feedback: str = ""
    grader_model: str = "ollama"


@dataclass
class EvaluationReport:
    """Aggregated evaluation results."""

    prompt_module: str
    total_tests: int
    passed: int
    failed: int
    accuracy: float
    breakdown_by_importance: dict[str, dict]
    results: list[TestResult]
    executed_at: str
    threshold: float
    threshold_passed: bool
    average_score: float | None = None
    graded_count: int = 0
    quality_threshold: float | None = None
    quality_threshold_passed: bool | None = None
    previous_report_path: str | None = None


def validate_chat_rag_response(response: str, expected: dict) -> bool:
    """Validates chat_rag response against expected criteria.

    `must_contain` requires ALL terms present (AND) — use for checking a
    response covers multiple distinct facts.
    `must_contain_any` requires AT LEAST ONE term present (OR) — use for
    refusal/rejection checks, since a model can phrase "out of scope" many
    different ways (matches the marker-list pattern in test_rag_boundaries.py).
    """
    response_lower = response.lower()

    must_contain = expected.get("must_contain", [])
    if must_contain:
        for term in must_contain:
            if term.lower() not in response_lower:
                return False

    must_contain_any = expected.get("must_contain_any", [])
    if must_contain_any:
        if not any(term.lower() in response_lower for term in must_contain_any):
            return False

    must_not_contain = expected.get("must_not_contain", [])
    if must_not_contain:
        for term in must_not_contain:
            if term.lower() in response_lower:
                return False

    return True


def validate_risk_explanation(explanation: dict, expected: dict) -> bool:
    """Validates risk explanation structure and content."""
    # Check title exists
    if expected.get("has_title") and not explanation.get("title"):
        return False

    # Check factors exist and non-empty
    if expected.get("has_factors"):
        factors = explanation.get("factors", [])
        if not factors or not isinstance(factors, list):
            return False

    # Check urgency value
    urgency_expected = expected.get("urgency_value")
    if urgency_expected:
        if explanation.get("urgency") != urgency_expected:
            return False

    # Check must_contain in rendered text
    text = explanation.get("_rendered_text", "")
    must_contain = expected.get("must_contain", [])
    if must_contain:
        for term in must_contain:
            if term.lower() not in text.lower():
                return False

    # Check must_not_contain
    must_not_contain = expected.get("must_not_contain", [])
    if must_not_contain:
        for term in must_not_contain:
            if term.lower() in text.lower():
                return False

    return True


def validate_slack_webhook(payload: dict, expected: dict) -> bool:
    """Validates Slack webhook payload structure."""
    # Check valid JSON (already parsed, so it's valid)
    if expected.get("is_valid_json") and not isinstance(payload, dict):
        return False

    # Check has blocks
    if expected.get("has_blocks"):
        blocks = payload.get("blocks", [])
        if not blocks or not isinstance(blocks, list):
            return False

    # Check block count
    min_blocks = expected.get("block_count_gte")
    if min_blocks:
        if len(payload.get("blocks", [])) < min_blocks:
            return False

    # Flatten payload to string for text search. ensure_ascii=False is required —
    # json.dumps() escapes accented chars (Crítico -> Crítico) by default,
    # which silently breaks Spanish-text `must_contain_text` checks.
    payload_str = json.dumps(payload, ensure_ascii=False).lower()

    # Check must_contain_text
    must_contain = expected.get("must_contain_text", [])
    if must_contain:
        for term in must_contain:
            if term.lower() not in payload_str:
                return False

    return True


def generate_report(
    prompt_module: str,
    test_results: list[TestResult],
    threshold: float = 0.90,
    executed_at: str | None = None,
    quality_threshold: float | None = None,
    previous_report_path: Path | str | None = None,
) -> EvaluationReport:
    """Generates evaluation report from test results.

    If `test_results` are `GradedTestResult` with non-None scores, also
    computes `average_score` (1-10) alongside the binary accuracy.
    """
    if not executed_at:
        executed_at = datetime.now().isoformat()

    total = len(test_results)
    passed = sum(1 for r in test_results if r.passed)
    failed = total - passed
    accuracy = passed / total if total > 0 else 0.0

    # Breakdown by importance (requires test config metadata)
    breakdown = {
        "high": {"total": 0, "passed": 0},
        "medium": {"total": 0, "passed": 0},
        "low": {"total": 0, "passed": 0},
    }

    scored = [
        r.score for r in test_results if isinstance(r, GradedTestResult) and r.score is not None
    ]
    average_score = sum(scored) / len(scored) if scored else None
    quality_threshold_passed = (
        average_score >= quality_threshold
        if (average_score is not None and quality_threshold is not None)
        else None
    )

    return EvaluationReport(
        prompt_module=prompt_module,
        total_tests=total,
        passed=passed,
        failed=failed,
        accuracy=accuracy,
        breakdown_by_importance=breakdown,
        results=test_results,
        executed_at=executed_at,
        threshold=threshold,
        threshold_passed=accuracy >= threshold,
        average_score=average_score,
        graded_count=len(scored),
        quality_threshold=quality_threshold,
        quality_threshold_passed=quality_threshold_passed,
        previous_report_path=str(previous_report_path) if previous_report_path else None,
    )


def find_latest_report(output_dir: Path | str, prompt_module: str) -> Path | None:
    """Finds the most recent saved report for a prompt module, if any.

    Used to compute "vs previous run" deltas without keeping in-memory state
    between separate CLI/pytest invocations of the eval skill.
    """
    output_dir = Path(output_dir)
    module_name = prompt_module.split("/")[-1]
    candidates = sorted(output_dir.glob(f"{module_name}_*.json"))
    return candidates[-1] if candidates else None


def load_report_dict(path: Path | str) -> dict:
    """Loads a previously saved report JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def save_report(report: EvaluationReport, output_dir: Path | str) -> Path:
    """Saves evaluation report to JSON file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{report.prompt_module.split('/')[-1]}_{timestamp}.json"
    filepath = output_dir / filename

    # Convert report to dict
    report_dict = {
        "prompt_module": report.prompt_module,
        "total_tests": report.total_tests,
        "passed": report.passed,
        "failed": report.failed,
        "accuracy": f"{report.accuracy * 100:.1f}%",
        "threshold": f"{report.threshold * 100:.0f}%",
        "threshold_passed": report.threshold_passed,
        "average_score": round(report.average_score, 2)
        if report.average_score is not None
        else None,
        "graded_count": report.graded_count,
        "quality_threshold": report.quality_threshold,
        "quality_threshold_passed": report.quality_threshold_passed,
        "executed_at": report.executed_at,
        "results": [
            {
                "test_id": r.test_id,
                "passed": r.passed,
                "error": r.error,
                "duration_ms": r.duration_ms,
                **(
                    {
                        "score": r.score,
                        "grader_feedback": r.grader_feedback,
                        "grader_model": r.grader_model,
                    }
                    if isinstance(r, GradedTestResult)
                    else {}
                ),
            }
            for r in report.results
        ],
    }

    with open(filepath, "w") as f:
        json.dump(report_dict, f, indent=2)

    return filepath


def load_test_cases(config_file: Path | str) -> dict:
    """Loads test cases from JSON config file."""
    with open(config_file, "r") as f:
        return json.load(f)


def format_report_summary(report: EvaluationReport) -> str:
    """Formats evaluation report for console output."""
    emoji_pass = "✅" if report.threshold_passed else "❌"
    status = "PASS" if report.threshold_passed else "FAIL"

    lines = [
        f"\n{'=' * 60}",
        f"📊 EVALUATION REPORT: {report.prompt_module}",
        f"{'=' * 60}",
        f"Overall Accuracy: {report.passed}/{report.total_tests} ({report.accuracy * 100:.1f}%)",
        f"Threshold: {report.threshold * 100:.0f}% {emoji_pass} {status}",
        f"Executed: {report.executed_at}",
        f"{'=' * 60}\n",
    ]

    if report.results and any(not r.passed for r in report.results):
        lines.append("Failed Tests:")
        for result in report.results:
            if not result.passed:
                error_msg = result.error or "Unknown error"
                lines.append(f"  ❌ {result.test_id}: {error_msg}")
        lines.append("")

    return "\n".join(lines)


def format_graded_report_summary(
    report: EvaluationReport,
    previous_report: dict | None = None,
) -> str:
    """Formats a graded evaluation report for console output.

    Includes average quality score (1-10), per-test score + feedback, and
    a delta vs `previous_report` (a dict loaded via `load_report_dict`) when
    available, so iterating on a prompt shows whether a change actually
    helped instead of just "different".
    """
    emoji_acc = "✅" if report.threshold_passed else "❌"
    status_acc = "PASS" if report.threshold_passed else "FAIL"

    lines = [
        f"\n{'=' * 60}",
        f"📊 EVALUATION REPORT (GRADED): {report.prompt_module}",
        f"{'=' * 60}",
        f"Overall Accuracy: {report.passed}/{report.total_tests} ({report.accuracy * 100:.1f}%)",
        f"Threshold (Accuracy): {report.threshold * 100:.0f}% {emoji_acc} {status_acc}",
    ]

    if report.average_score is not None:
        emoji_q = "✅" if report.quality_threshold_passed in (True, None) else "❌"
        status_q = "PASS" if report.quality_threshold_passed in (True, None) else "FAIL"
        threshold_line = (
            f" | Threshold: {report.quality_threshold}/10 {emoji_q} {status_q}"
            if report.quality_threshold is not None
            else ""
        )
        lines.append(
            f"Average Quality Score: {report.average_score:.1f}/10 "
            f"({report.graded_count}/{report.total_tests} graded){threshold_line}"
        )
    else:
        lines.append("Average Quality Score: N/A (grading unavailable — Ollama down?)")

    lines.append(f"Executed: {report.executed_at}")
    lines.append(f"{'=' * 60}\n")

    lines.append("Per-Test Breakdown:")
    for r in report.results:
        status = "✅" if r.passed else "❌"
        score_part = ""
        if isinstance(r, GradedTestResult):
            if r.score is not None:
                score_part = f' (score {r.score}/10) - "{r.grader_feedback}"'
            else:
                score_part = f" (score N/A - {r.grader_feedback})"
        lines.append(f"  {status} {r.test_id}: {'PASS' if r.passed else 'FAIL'}{score_part}")
    lines.append("")

    if previous_report:
        prev_accuracy = previous_report.get("accuracy", "N/A")
        prev_score = previous_report.get("average_score")
        lines.append(f"Comparison vs Last Run ({previous_report.get('executed_at', 'unknown')}):")
        lines.append(f"  Accuracy: {prev_accuracy} → {report.accuracy * 100:.1f}%")
        if prev_score is not None and report.average_score is not None:
            delta = report.average_score - prev_score
            arrow = "+" if delta >= 0 else ""
            emoji = "✅" if delta >= 0 else "⚠️"
            lines.append(
                f"  Quality: {prev_score:.1f} → {report.average_score:.1f} ({arrow}{delta:.1f}) {emoji}"
            )
        lines.append("")

    return "\n".join(lines)


# ── Grader comparison (Ollama vs Anthropic) ─────────────────────────────────


@dataclass
class GraderComparison:
    """One test case scored by two different judge providers, for agreement
    analysis — same artifact, same rubric prompt, different judge model."""

    test_id: str
    ollama_score: int | None
    anthropic_score: int | None
    ollama_feedback: str
    anthropic_feedback: str

    @property
    def delta(self) -> int | None:
        if self.ollama_score is None or self.anthropic_score is None:
            return None
        return self.anthropic_score - self.ollama_score


def save_comparison_report(
    domain: str,
    comparisons: list[GraderComparison],
    output_dir: Path | str,
    executed_at: str | None = None,
) -> Path:
    """Saves a grader-comparison report (Ollama vs Anthropic) to JSON.

    Summary stats only cover pairs where both graders returned a score —
    a grader outage on one side lowers `paired_count`, not the average.
    """
    if not executed_at:
        executed_at = datetime.now().isoformat()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paired = [
        c for c in comparisons if c.ollama_score is not None and c.anthropic_score is not None
    ]
    deltas = [c.delta for c in paired]
    avg_ollama = sum(c.ollama_score for c in paired) / len(paired) if paired else None
    avg_anthropic = sum(c.anthropic_score for c in paired) / len(paired) if paired else None
    mean_abs_delta = sum(abs(d) for d in deltas) / len(deltas) if deltas else None
    high_disagreement = [c.test_id for c in paired if abs(c.delta) >= 3]

    report_dict = {
        "domain": domain,
        "executed_at": executed_at,
        "total_cases": len(comparisons),
        "paired_count": len(paired),
        "average_ollama_score": round(avg_ollama, 2) if avg_ollama is not None else None,
        "average_anthropic_score": round(avg_anthropic, 2) if avg_anthropic is not None else None,
        "mean_absolute_delta": round(mean_abs_delta, 2) if mean_abs_delta is not None else None,
        "high_disagreement_cases": high_disagreement,
        "results": [
            {
                "test_id": c.test_id,
                "ollama_score": c.ollama_score,
                "anthropic_score": c.anthropic_score,
                "delta": c.delta,
                "ollama_feedback": c.ollama_feedback,
                "anthropic_feedback": c.anthropic_feedback,
            }
            for c in comparisons
        ],
    }

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = output_dir / f"grader_comparison_{domain}_{timestamp}.json"
    with open(filepath, "w") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    return filepath


def format_comparison_summary(domain: str, comparisons: list[GraderComparison]) -> str:
    """Formats a grader-comparison report for console output."""
    paired = [
        c for c in comparisons if c.ollama_score is not None and c.anthropic_score is not None
    ]
    avg_ollama = sum(c.ollama_score for c in paired) / len(paired) if paired else None
    avg_anthropic = sum(c.anthropic_score for c in paired) / len(paired) if paired else None
    mean_abs_delta = sum(abs(c.delta) for c in paired) / len(paired) if paired else None

    lines = [
        f"\n{'=' * 70}",
        f"⚖️  GRADER COMPARISON (Ollama vs Anthropic): {domain}",
        f"{'=' * 70}",
    ]
    if avg_ollama is not None and avg_anthropic is not None:
        lines.append(
            f"Average score — Ollama: {avg_ollama:.1f}/10  |  Anthropic: {avg_anthropic:.1f}/10"
        )
        lines.append(
            f"Mean absolute delta: {mean_abs_delta:.1f} points ({len(paired)}/{len(comparisons)} paired)"
        )
    else:
        lines.append("No paired scores available (a grader failed on every case)")
    lines.append(f"{'=' * 70}\n")

    lines.append(f"{'test_id':<28} {'ollama':>7} {'claude':>7} {'delta':>7}")
    for c in comparisons:
        o = str(c.ollama_score) if c.ollama_score is not None else "N/A"
        a = str(c.anthropic_score) if c.anthropic_score is not None else "N/A"
        d = f"{c.delta:+d}" if c.delta is not None else "N/A"
        lines.append(f"{c.test_id:<28} {o:>7} {a:>7} {d:>7}")

    high_disagreement = [c for c in paired if abs(c.delta) >= 3]
    if high_disagreement:
        lines.append("\nHigh disagreement (|delta| >= 3):")
        for c in high_disagreement:
            lines.append(f'  {c.test_id}: ollama={c.ollama_score} ("{c.ollama_feedback}")')
            lines.append(
                f'  {" " * len(c.test_id)}  claude={c.anthropic_score} ("{c.anthropic_feedback}")'
            )

    return "\n".join(lines)
