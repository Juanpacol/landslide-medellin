"""In-process orchestrator: named composition of steps with dependencies and
structured traceability. No new infrastructure (no Redis/Kafka/queues) —
a deliberate architecture decision for this project.

Formalizes the pattern that used to live scattered across `fire_alerts.py`
(each function wrapped its calls in its own try/except + logger.exception).
Doesn't replace that contract, makes it explicit: a non-critical step that
fails is logged and does NOT block its dependents — same behavior as
today ("a downed Slack must not take down alerts or predictions").

Deliberate scope — what this module does NOT orchestrate:
- Cross-workflow (scraper → predict in GitHub Actions): the 6 crons remain
  independent, no `needs:`/`workflow_run`. Chaining them would be new
  orchestration infrastructure, even if it costs nothing.
- The retry declared in `Step.retries` is a capability of the module, not
  something used today in `fire_alerts.py`'s steps: those checks aren't
  safely idempotent at the whole-step level (they could re-mark cooldown).
  The real, safe retry already lives in
  `infrastructure/external/slack_client.py::post_webhook`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from errors.error_handler import TransientError, retry_transient_call

logger = logging.getLogger(__name__)


@dataclass
class Step:
    name: str
    fn: Callable[[], Awaitable[Any]]
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    critical: bool = False


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "skipped" | "error"
    error: str | None = None
    duration_ms: float = 0.0


def _topological_order(steps: list[Step]) -> list[Step]:
    """Simple ordering over `depends_on`. No parallelism: current volume
    (2-3 steps per composition) doesn't justify it."""
    by_name = {s.name: s for s in steps}
    ordered: list[Step] = []
    seen: set[str] = set()

    def visit(step: Step) -> None:
        if step.name in seen:
            return
        for dep_name in step.depends_on:
            dep = by_name.get(dep_name)
            if dep is not None:
                visit(dep)
        seen.add(step.name)
        ordered.append(step)

    for step in steps:
        visit(step)
    return ordered


async def run_steps(steps: list[Step]) -> list[StepResult]:
    """Runs the steps in topological order. A step whose dependency failed
    (and that dependency is `critical=True`) is skipped (`status="skipped"`);
    otherwise it runs anyway — same spirit as "a downed check doesn't take
    down the others"."""
    ordered = _topological_order(steps)
    results: dict[str, StepResult] = {}

    for step in ordered:
        blocked_by = [
            dep
            for dep in step.depends_on
            if dep in results
            and results[dep].status == "error"
            and next((s for s in ordered if s.name == dep), None) is not None
            and next(s for s in ordered if s.name == dep).critical
        ]
        if blocked_by:
            results[step.name] = StepResult(
                name=step.name,
                status="skipped",
                error=f"critical dependency failed: {blocked_by}",
            )
            logger.warning(
                "orchestrator: step '%s' skipped, critical dependency failed",
                step.name,
                extra={"step": step.name, "status": "skipped"},
            )
            continue

        started = time.monotonic()
        try:
            if step.retries > 0:
                await retry_transient_call(
                    step.fn, attempts=step.retries, exceptions=(TransientError,)
                )
            else:
                await step.fn()
            duration_ms = (time.monotonic() - started) * 1000
            results[step.name] = StepResult(name=step.name, status="ok", duration_ms=duration_ms)
            logger.info(
                "orchestrator: step '%s' ok (%.0fms)",
                step.name,
                duration_ms,
                extra={"step": step.name, "status": "ok", "duration_ms": duration_ms},
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.monotonic() - started) * 1000
            results[step.name] = StepResult(
                name=step.name, status="error", error=str(exc), duration_ms=duration_ms
            )
            logger.exception(
                "orchestrator: step '%s' failed (%.0fms)",
                step.name,
                duration_ms,
                extra={"step": step.name, "status": "error", "duration_ms": duration_ms},
            )

    return [results[s.name] for s in ordered]
