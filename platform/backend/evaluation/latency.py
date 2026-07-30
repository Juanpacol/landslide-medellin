"""Inference latency p50/p95 — ML-only vs. neuro-symbolic (specs/007-experimental-eval/spec.md
task: "inference latency p50/p95, ML vs neuro-symbolic"). Measures the pure computation only
(`domain.risk_rules.risk_level_from_score` vs.
`application.neurosymbolic.infer.resolve_verdict`) — neither touches the DB, so this isolates
what the symbolic layer actually costs on top of the neural score, without I/O noise from
`ml/hazard.py`'s queries dominating the number.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from application.neurosymbolic.infer import resolve_verdict
from domain.risk_rules import risk_level_from_score
from domain.rules.facts import TerritorySnapshot


@dataclass(frozen=True)
class LatencyReport:
    arm: str
    n_runs: int
    p50_ms: float
    p95_ms: float
    mean_ms: float


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(round(pct * (len(sorted_values) - 1))))
    return sorted_values[idx]


def _summarize(arm: str, durations_ms: list[float]) -> LatencyReport:
    ordered = sorted(durations_ms)
    n = len(ordered)
    return LatencyReport(
        arm=arm,
        n_runs=n,
        p50_ms=round(_percentile(ordered, 0.50), 4),
        p95_ms=round(_percentile(ordered, 0.95), 4),
        mean_ms=round(sum(ordered) / n, 4) if n else 0.0,
    )


def benchmark_ml_only(scores: list[float], *, repeats: int = 1) -> LatencyReport:
    durations: list[float] = []
    for _ in range(repeats):
        for score in scores:
            start = time.perf_counter()
            risk_level_from_score(score)
            durations.append((time.perf_counter() - start) * 1000)
    return _summarize("ml_only", durations)


def benchmark_neurosymbolic(
    cases: list[tuple[str, float | None, TerritorySnapshot]], *, repeats: int = 1
) -> LatencyReport:
    durations: list[float] = []
    for _ in range(repeats):
        for commune_id, score, snapshot in cases:
            start = time.perf_counter()
            resolve_verdict(commune_id, score, snapshot)
            durations.append((time.perf_counter() - start) * 1000)
    return _summarize("neurosymbolic", durations)
