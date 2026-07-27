"""
Parametrized evaluation tests for chat_rag prompt.

These tests load test cases from tests/eval_config/chat_rag.json and
validate that chat_rag responses match expected criteria (in-scope vs
out-of-scope, variants, etc.).

Run with: pytest tests/test_eval_chat_rag.py -v
Or use the /eval-prompt skill: /eval-prompt chat_rag
"""

import json
import uuid
from pathlib import Path

import pytest

from agent.chat_rag import chat_rag
from tests.eval_runner import (
    TestResult,
    format_report_summary,
    generate_report,
    save_report,
    validate_chat_rag_response,
)

CONFIG_FILE = Path(__file__).parent / "eval_config" / "chat_rag.json"
RESULTS_DIR = Path(__file__).parent / "eval_results"


@pytest.fixture
def chat_rag_config():
    """Load chat_rag test configuration."""
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_chat_rag_batch_evaluation(db_session, require_ollama, chat_rag_config):
    """Run all chat_rag tests and generate report.

    Uses a single event loop (pytest-asyncio's) for every case, reusing the
    same `db_session` — `asyncio.run()` per case would spin up a fresh loop
    per call and break the shared asyncpg connection ("another operation is
    in progress").
    """
    test_cases = chat_rag_config["test_cases"]
    results = []

    for test_case in test_cases:
        session_id = f"eval-chat-rag-{uuid.uuid4()}"

        try:
            response = await chat_rag(test_case["input"], session_id, db_session)
            is_valid = validate_chat_rag_response(response, test_case["expected"])

            result = TestResult(
                test_id=test_case["id"],
                passed=is_valid,
                expected=test_case["expected"],
                actual=response[:100],
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
        prompt_module="agent/chat_rag",
        test_results=results,
        threshold=0.90,
    )

    save_report(report, RESULTS_DIR)
    print(format_report_summary(report))

    # Assert threshold
    assert report.threshold_passed, (
        f"Chat RAG accuracy {report.accuracy * 100:.1f}% below threshold {report.threshold * 100:.0f}%"
    )
