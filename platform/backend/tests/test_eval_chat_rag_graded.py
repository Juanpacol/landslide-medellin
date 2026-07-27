"""
Graded evaluation for chat_rag — adds a 1-10 Ollama-judge quality score on
top of the binary pass/fail validation in test_eval_chat_rag.py.

Requires Ollama running (skips otherwise, same as test_rag_boundaries.py).
Slower than the binary-only suite (2 Ollama calls per test case: 1 to get
the response, 1 to grade it) — run this when iterating on prompt quality,
not on every save.

Run with: pytest tests/test_eval_chat_rag_graded.py -v -s
Or use the /eval-prompt skill: /eval-prompt chat_rag --grading
"""

import json
import uuid
from pathlib import Path

import pytest

from agent.chat_rag import chat_rag
from tests.eval_grader import grade_chat_rag_response
from tests.eval_runner import (
    GradedTestResult,
    find_latest_report,
    format_graded_report_summary,
    generate_report,
    load_report_dict,
    save_report,
    validate_chat_rag_response,
)

CONFIG_FILE = Path(__file__).parent / "eval_config" / "chat_rag.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"
QUALITY_THRESHOLD = 7.0


@pytest.fixture
def chat_rag_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_chat_rag_graded_evaluation(db_session, require_ollama, chat_rag_config):
    """Runs all chat_rag test cases, grading each response 1-10 via Ollama."""
    test_cases = chat_rag_config["test_cases"]

    # Snapshot the previous report (if any) BEFORE this run overwrites it,
    # so the printed comparison reflects the prior run, not this one.
    previous_path = find_latest_report(RESULTS_DIR, "agent/chat_rag_graded")
    previous_report = load_report_dict(previous_path) if previous_path else None

    results: list[GradedTestResult] = []

    for test_case in test_cases:
        session_id = f"eval-chat-rag-graded-{uuid.uuid4()}"

        try:
            response = await chat_rag(test_case["input"], session_id, db_session)
            is_valid = validate_chat_rag_response(response, test_case["expected"])
            graded = await grade_chat_rag_response(test_case["input"], response)

            results.append(
                GradedTestResult(
                    test_id=test_case["id"],
                    passed=is_valid,
                    expected=test_case["expected"],
                    actual=response[:200],
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
        prompt_module="agent/chat_rag_graded",
        test_results=results,
        threshold=0.90,
        quality_threshold=QUALITY_THRESHOLD,
    )

    save_report(report, RESULTS_DIR)
    print(format_graded_report_summary(report, previous_report))

    assert report.threshold_passed, (
        f"Chat RAG accuracy {report.accuracy * 100:.1f}% below threshold {report.threshold * 100:.0f}%"
    )
    if report.average_score is not None:
        assert report.average_score >= QUALITY_THRESHOLD, (
            f"Chat RAG quality score {report.average_score:.1f}/10 below threshold {QUALITY_THRESHOLD}/10"
        )
