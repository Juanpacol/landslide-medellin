"""Reproduces every number in `docs/research/paper.md` §5. Pure computation,
no DB, no API keys — see the module docstrings in `evaluation/` for what each
metric means and why it's computed this way.

Usage:

    cd platform/backend && PYTHONPATH=. python -m evaluation.reproduce_paper
"""

from __future__ import annotations

import random

from application.neurosymbolic.infer import resolve_verdict
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.ablation import AblationCase, run_ablation
from evaluation.latency import benchmark_ml_only, benchmark_neurosymbolic
from evaluation.primary_metrics import rule_coverage
from evaluation.run import arms_disagree, run_all_arms

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


def main() -> None:
    rng = random.Random(_SEED)
    snapshots = _build_snapshots(rng)

    print("## §5.2 Rule coverage")
    report = rule_coverage(snapshots, CATALOG)
    print(f"n_snapshots={report.n_snapshots} pct_any_fired={report.pct_snapshots_with_any_fired_rule}")
    for rule_id, rate in report.fire_rate_by_rule.items():
        print(f"  {rule_id}: fire={rate:.2f} evaluable={report.evaluable_rate_by_rule[rule_id]:.2f}")

    print("\n## §5.3 Ablation")
    rng2 = random.Random(_SEED)  # fresh sequence, matches paper.md's independent score draw
    cases = [AblationCase(s.commune_id, rng2.uniform(0, 1), s) for s in snapshots]
    ablation_rules = run_ablation("rules", cases)
    ablation_quality = run_ablation("quality", cases)
    print(
        f"rules: n_changed={ablation_rules.n_level_changed}/{ablation_rules.n_cases} "
        f"pct={ablation_rules.pct_level_changed} conf_delta={ablation_rules.confidence_delta_mean}"
    )
    print(
        f"quality: n_changed={ablation_quality.n_level_changed} "
        f"conf_delta={ablation_quality.confidence_delta_mean}"
    )

    n_disagree = 0
    for case in cases:
        arms = run_all_arms(case.commune_id, case.neural_score, case.snapshot)
        if arms_disagree(arms):
            n_disagree += 1
    print(f"arms disagree on {n_disagree}/{len(snapshots)}")

    print("\n## §5.5 Latency")
    scores = [rng.uniform(0, 1) for _ in range(210)]
    ml_report = benchmark_ml_only(scores, repeats=10)
    print(f"ml_only: p50={ml_report.p50_ms}ms p95={ml_report.p95_ms}ms")

    ns_cases = [(s.commune_id, rng.uniform(0, 1), s) for s in snapshots]
    ns_report = benchmark_neurosymbolic(ns_cases, repeats=50)
    print(f"neurosymbolic: p50={ns_report.p50_ms}ms p95={ns_report.p95_ms}ms")

    # Sanity check the pure function is actually deterministic — resolve_verdict
    # must give the same answer twice for the same inputs (specs/002-rule-engine/).
    s0 = snapshots[0]
    assert resolve_verdict(s0.commune_id, 0.5, s0) == resolve_verdict(s0.commune_id, 0.5, s0)


if __name__ == "__main__":
    main()
