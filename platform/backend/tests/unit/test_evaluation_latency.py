"""Tests for evaluation/latency.py — pure timing, no DB.

Not asserting specific millisecond thresholds (machine-dependent); asserting
shape (p95 >= p50, both non-negative) and that the harness runs both arms
end to end.
"""

from __future__ import annotations

from domain.rules.facts import TerritorySnapshot
from evaluation.latency import benchmark_ml_only, benchmark_neurosymbolic


def test_ml_only_report_shape():
    report = benchmark_ml_only([0.1, 0.5, 0.8, 0.95], repeats=5)
    assert report.arm == "ml_only"
    assert report.n_runs == 20
    assert report.p95_ms >= report.p50_ms >= 0.0
    assert report.mean_ms >= 0.0


def test_neurosymbolic_report_shape():
    cases = [
        ("8", 0.1, TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)),
        ("1", 0.5, TerritorySnapshot(commune_id="1", precip_72h_mm=5.0)),
    ]
    report = benchmark_neurosymbolic(cases, repeats=5)
    assert report.arm == "neurosymbolic"
    assert report.n_runs == 10
    assert report.p95_ms >= report.p50_ms >= 0.0


def test_empty_input_returns_zeroed_report():
    report = benchmark_ml_only([])
    assert report.n_runs == 0
    assert report.p50_ms == 0.0
    assert report.p95_ms == 0.0
