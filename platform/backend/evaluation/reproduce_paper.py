"""Reproduces every number in `docs/research/paper.md` §5. Pure computation,
no DB, no API keys — see the module docstrings in `evaluation/` for what each
metric means and why it's computed this way.

Usage:

    cd platform/backend && PYTHONPATH=. python -m evaluation.reproduce_paper
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.neurosymbolic.infer import resolve_verdict
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.ablation import AblationCase, run_ablation
from evaluation.latency import benchmark_ml_only, benchmark_neurosymbolic
from evaluation.primary_metrics import rule_coverage
from evaluation.run import arms_disagree, run_all_arms
from evaluation.stability import StabilityCase, counterfactual_stability

# Same seed and coverage rates as used to write paper.md §5 — the point of
# fixing the seed here is that anyone running this file gets the exact
# numbers quoted in the paper, not "numbers in the same ballpark".
_SEED = 42

# Coverage rates chosen to match today's real data-availability pattern:
# terrain slope now populated (SPEC-006's SRTM ingestion), rain/SWI still
# gapped (the audit's rainfall corruption finding), seismic and
# critical-facility proximity partial.
_P_RAIN = 0.3
_P_SLOPE = 0.9
_P_SEISMIC = 0.5
_N_COMMUNES = 21


def _build_snapshots(rng: random.Random) -> list[TerritorySnapshot]:
    snapshots = []
    for i in range(1, _N_COMMUNES + 1):
        cid = str(i)
        has_rain = rng.random() < _P_RAIN
        has_slope = rng.random() < _P_SLOPE
        snapshots.append(
            TerritorySnapshot(
                commune_id=cid,
                slope_p90_deg=rng.uniform(5, 45) if has_slope else None,
                hazard_fraction=rng.uniform(0, 1),
                precip_72h_mm=rng.uniform(0, 180) if has_rain else None,
                swi_pct=rng.uniform(0, 100) if has_rain else None,
                seismic_intensity=rng.uniform(0, 25) if rng.random() < _P_SEISMIC else None,
                prior_event_count=rng.choice([0, 0, 1, 2]),
                nearest_critical_facility_m=rng.choice([None, 50, 300, 1000]),
            )
        )
    return snapshots


def collect_results() -> dict[str, Any]:
    """Runs every §5.2/§5.3/§5.5 computation and returns a JSON-serializable
    dict — used both by `main()`'s printed report and by the CI workflow,
    which writes this straight to `evaluation/results/`."""
    rng = random.Random(_SEED)
    snapshots = _build_snapshots(rng)

    coverage = rule_coverage(snapshots, CATALOG)

    rng2 = random.Random(_SEED)  # fresh sequence, matches paper.md's independent score draw
    cases = [AblationCase(s.commune_id, rng2.uniform(0, 1), s) for s in snapshots]
    ablation_rules = run_ablation("rules", cases)
    ablation_quality = run_ablation("quality", cases)

    stability_cases = [StabilityCase(c.commune_id, c.neural_score, c.snapshot) for c in cases]
    stability = counterfactual_stability(stability_cases, CATALOG)

    n_disagree = sum(
        1
        for case in cases
        if arms_disagree(run_all_arms(case.commune_id, case.neural_score, case.snapshot))
    )

    scores = [rng.uniform(0, 1) for _ in range(210)]
    ml_report = benchmark_ml_only(scores, repeats=10)
    ns_cases = [(s.commune_id, rng.uniform(0, 1), s) for s in snapshots]
    ns_report = benchmark_neurosymbolic(ns_cases, repeats=50)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": _SEED,
        "rule_coverage": {
            "n_snapshots": coverage.n_snapshots,
            "pct_any_fired": coverage.pct_snapshots_with_any_fired_rule,
            "fire_rate_by_rule": coverage.fire_rate_by_rule,
            "evaluable_rate_by_rule": coverage.evaluable_rate_by_rule,
        },
        "ablation": {
            "rules": {
                "n_changed": ablation_rules.n_level_changed,
                "n_cases": ablation_rules.n_cases,
                "pct_changed": ablation_rules.pct_level_changed,
                "confidence_delta_mean": ablation_rules.confidence_delta_mean,
            },
            "quality": {
                "n_changed": ablation_quality.n_level_changed,
                "confidence_delta_mean": ablation_quality.confidence_delta_mean,
            },
        },
        "counterfactual_stability": {
            "perturbation_pct": stability.perturbation_pct,
            "n_eligible": stability.n_eligible,
            "pct_level_changed": stability.pct_level_changed,
            "pct_vetoed_changed": stability.pct_vetoed_changed,
        },
        "four_arm_disagreement": {"n_disagree": n_disagree, "n_total": len(snapshots)},
        "latency_ms": {
            "ml_only": {"p50": ml_report.p50_ms, "p95": ml_report.p95_ms},
            "neurosymbolic": {"p50": ns_report.p50_ms, "p95": ns_report.p95_ms},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write results as JSON to this path (e.g. evaluation/results/<timestamp>.json)",
    )
    args = parser.parse_args()

    results = collect_results()

    print("## §5.2 Rule coverage")
    rc = results["rule_coverage"]
    print(f"n_snapshots={rc['n_snapshots']} pct_any_fired={rc['pct_any_fired']}")
    for rule_id, rate in rc["fire_rate_by_rule"].items():
        print(f"  {rule_id}: fire={rate:.2f} evaluable={rc['evaluable_rate_by_rule'][rule_id]:.2f}")

    print("\n## §5.3 Ablation")
    ar = results["ablation"]["rules"]
    aq = results["ablation"]["quality"]
    print(
        f"rules: n_changed={ar['n_changed']}/{ar['n_cases']} "
        f"pct={ar['pct_changed']} conf_delta={ar['confidence_delta_mean']}"
    )
    print(f"quality: n_changed={aq['n_changed']} conf_delta={aq['confidence_delta_mean']}")

    cs = results["counterfactual_stability"]
    print(
        f"\n## Counterfactual stability (±{cs['perturbation_pct'] * 100:.0f}% rain)\n"
        f"n_eligible={cs['n_eligible']} pct_level_changed={cs['pct_level_changed']} "
        f"pct_vetoed_changed={cs['pct_vetoed_changed']}"
    )

    disagreement = results["four_arm_disagreement"]
    print(f"arms disagree on {disagreement['n_disagree']}/{disagreement['n_total']}")

    print("\n## §5.5 Latency")
    lat = results["latency_ms"]
    print(f"ml_only: p50={lat['ml_only']['p50']}ms p95={lat['ml_only']['p95']}ms")
    print(f"neurosymbolic: p50={lat['neurosymbolic']['p50']}ms p95={lat['neurosymbolic']['p95']}ms")

    # Sanity check the pure function is actually deterministic — resolve_verdict
    # must give the same answer twice for the same inputs (specs/002-rule-engine/).
    rng = random.Random(_SEED)
    s0 = _build_snapshots(rng)[0]
    assert resolve_verdict(s0.commune_id, 0.5, s0) == resolve_verdict(s0.commune_id, 0.5, s0)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
