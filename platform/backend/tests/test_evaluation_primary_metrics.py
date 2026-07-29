"""Tests for evaluation/primary_metrics.py — the metrics specs/007-experimental-eval/spec.md
can compute without any real landslide labels.
"""

from __future__ import annotations

from application.neurosymbolic.explain import render
from application.neurosymbolic.infer import resolve_verdict
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.primary_metrics import explanation_faithfulness, rule_coverage


def test_rule_coverage_empty_snapshots():
    report = rule_coverage([], CATALOG)
    assert report.n_snapshots == 0
    assert report.pct_snapshots_with_any_fired_rule == 0.0


def test_rule_coverage_reports_fire_rate_per_rule():
    snapshots = [
        TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0),  # R-GEO-01 fires
        TerritorySnapshot(commune_id="9", precip_72h_mm=5.0),  # no geotechnical rule fires
    ]
    report = rule_coverage(snapshots, CATALOG)
    assert report.n_snapshots == 2
    assert report.fire_rate_by_rule["R-GEO-01"] == 0.5
    assert 0.0 <= report.pct_snapshots_with_any_fired_rule <= 1.0


def test_rule_coverage_tracks_not_evaluable_rules():
    # No slope, no twi, no ndvi anywhere: R-GEO-02..04 can never evaluate.
    snapshots = [TerritorySnapshot(commune_id="1", precip_72h_mm=5.0)]
    report = rule_coverage(snapshots, CATALOG)
    assert report.evaluable_rate_by_rule["R-GEO-02"] == 0.0


def test_faithfulness_report_rate():
    snapshot = TerritorySnapshot(commune_id="8", slope_p90_deg=40.0, precip_72h_mm=150.0)
    verdict = resolve_verdict("8", 0.1, snapshot)
    tree = render(verdict)

    statements = [
        (["neural", "R-GEO-01"], tree),  # faithful
        (["neural", "R-GHOST-99"], tree),  # not faithful
    ]
    report = explanation_faithfulness(statements)
    assert report.n_statements == 2
    assert report.n_faithful == 1
    assert report.faithfulness_rate == 0.5
