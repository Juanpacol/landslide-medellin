"""Smoke test for evaluation/reproduce_paper.py — the script that generates
every number in docs/research/paper.md §5. Verifies it runs end to end and
that the deterministic (non-latency) numbers match what's quoted in the
paper, so the paper can't silently drift from the code.
"""

from __future__ import annotations

from domain.rules.catalog import CATALOG
from evaluation.ablation import AblationCase, run_ablation
from evaluation.primary_metrics import rule_coverage
from evaluation.reproduce_paper import _SEED, _build_snapshots
import random


def test_reproduce_paper_runs_without_error(monkeypatch):
    import sys

    from evaluation import reproduce_paper

    monkeypatch.setattr(sys, "argv", ["reproduce_paper"])
    reproduce_paper.main()  # must not raise


def test_collect_results_is_json_serializable():
    import json

    from evaluation.reproduce_paper import collect_results

    results = collect_results()
    json.dumps(results)  # must not raise
    assert results["rule_coverage"]["n_snapshots"] == 21
    assert "latency_ms" in results


def test_rule_coverage_numbers_match_the_paper():
    rng = random.Random(_SEED)
    snapshots = _build_snapshots(rng)
    report = rule_coverage(snapshots, CATALOG)

    assert report.n_snapshots == 21
    assert report.pct_snapshots_with_any_fired_rule == 0.7619
    assert round(report.fire_rate_by_rule["R-QUAL-01"], 2) == 0.43
    assert round(report.fire_rate_by_rule["R-HIST-01"], 2) == 0.43
    assert report.evaluable_rate_by_rule["R-GEO-03"] == 0.0  # TWI unpopulated


def test_ablation_numbers_match_the_paper():
    rng = random.Random(_SEED)
    snapshots = _build_snapshots(rng)
    rng2 = random.Random(_SEED)
    cases = [AblationCase(s.commune_id, rng2.uniform(0, 1), s) for s in snapshots]

    rules_result = run_ablation("rules", cases)
    assert rules_result.n_level_changed == 0
    assert rules_result.confidence_delta_mean == -0.1548
