"""Read-only spot-check of the neuro-symbolic pipeline against REAL Medellín production data
(Supabase). Unlike everything else in `evaluation/`, this does NOT run on synthetic
`TerritorySnapshot`s — it builds them from real per-commune data read from the actual
production database, then runs the same pure functions already tested on synthetic data.

## Why this exists

Every other `evaluation/*` module (and `docs/research/paper.md` §5) runs on synthetic snapshots
constructed to *approximate* today's real data-coverage pattern. This script instead asks: what
does the system actually say about the 21 real Medellín communes, right now, using real data?
It is a single-point-in-time spot-check, not a repeated measurement or a backtest — there is no
real historical event dataset to backtest against (`docs/research/audit-2026-07.md` §8).

## Safety — read-only, no exceptions

This script NEVER calls `application.predict_risk.run_predictions()`,
`ml.predict.predict_all_comunas()`, or any function that does `session.add()`/`session.commit()`.
Every DB interaction here is a `SELECT`, either directly or through existing read-only functions
(`ml.hazard.hazard_by_commune`, `infrastructure.repositories.landslide_events.real_events`). The
session is opened, used to read, and closed — nothing is written, no migration runs, no scraper
runs, no model retrains.

## Usage

    cd platform/backend && export PYTHONPATH=.
    python -m evaluation.validate_against_production --json-out /path/to/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.neurosymbolic.infer import resolve_verdict
from db.session import AsyncSessionLocal
from domain.communes import COMMUNES
from domain.quality import MIN_ROWS_FOR_DISTINCT_CHECK, is_frozen_signal
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.primary_metrics import rule_coverage
from evaluation.run import ARMS, arms_disagree, run_all_arms


async def _frozen_rain_flags(session) -> dict[str, bool]:
    """Real, per-commune check of `domain.quality.is_frozen_signal` against
    `rainfall_timeseries` (the same predicate `monitoring/scraper_validator.py` uses, now
    reused here to feed `TerritorySnapshot.quality_flags` — something no existing code
    path currently does: the inference engine's confidence penalty for a flagged source
    exists (`application/neurosymbolic/infer.py::_confidence`) but nothing was populating
    `quality_flags` from real data before this script).
    """
    from sqlalchemy import select

    from db.models.rainfall_timeseries import RainfallTimeseries

    stmt = (
        select(RainfallTimeseries.commune_id, RainfallTimeseries.precip_mm)
        .order_by(RainfallTimeseries.snapshot_at.desc())
        .limit(3000)
    )
    rows = (await session.execute(stmt)).all()
    by_commune: dict[str, list[float]] = {}
    for cid, val in rows:
        by_commune.setdefault(str(cid), []).append(val)

    return {
        cid: is_frozen_signal(vals, min_rows=MIN_ROWS_FOR_DISTINCT_CHECK)
        for cid, vals in by_commune.items()
    }


def _build_snapshot(
    commune_id: str, hazard: Any, prior_event_count: int, *, rain_is_frozen: bool
) -> TerritorySnapshot:
    """Same field mapping `application/neurosymbolic/infer.py::infer_all()` uses internally —
    duplicated here (not imported) because `infer_all()` doesn't expose the intermediate
    snapshot, only the final `Verdict`, and this script needs the snapshot itself to run
    `run_all_arms()`/`rule_coverage()` for comparison. `nearest_critical_facility_m` is honestly
    `None`: that data isn't persisted anywhere in Postgres today (only fetched live from
    Overpass into the in-memory `kg` graph, specs/005-knowledge-graph/).
    """
    swi = hazard.trigger_components.get("swi")
    return TerritorySnapshot(
        commune_id=commune_id,
        hazard_fraction=hazard.susceptibility_components.get("hazard"),
        slope_p90_deg=None,  # barrio_terrain is empty in production — see report §1
        twi_p90=None,
        ndvi_min=None,
        swi_pct=(swi * 100.0) if swi is not None else None,
        antecedent_mm=hazard.trigger_components.get("antecedent"),
        precip_72h_mm=hazard.trigger_components.get("antecedent"),
        seismic_intensity=hazard.trigger_components.get("seismic"),
        prior_event_count=prior_event_count,
        nearest_critical_facility_m=None,
        quality_flags=frozenset({"frozen_signal"}) if rain_is_frozen else frozenset(),
    )


async def _prior_event_counts(session) -> dict[str, int]:
    """Real, non-synthetic prior-event counts per commune, from `landslide_events`."""
    from infrastructure.repositories.landslide_events import real_events

    events = await real_events(session)
    counts: Counter[str] = Counter()
    for ev in events:
        if ev.commune_id:
            counts[str(ev.commune_id)] += 1
    return dict(counts)


async def collect_real_results() -> dict[str, Any]:
    from ml.hazard import hazard_by_commune

    async with AsyncSessionLocal() as session:
        hazards = await hazard_by_commune(session)
        prior_counts = await _prior_event_counts(session)
        frozen_flags = await _frozen_rain_flags(session)

        snapshots: dict[str, TerritorySnapshot] = {}
        neural_scores: dict[str, float | None] = {}
        for commune in COMMUNES:
            cid = commune.id
            hazard = hazards.get(cid)
            if hazard is None:
                continue
            snapshots[cid] = _build_snapshot(
                cid, hazard, prior_counts.get(cid, 0), rain_is_frozen=frozen_flags.get(cid, False)
            )
            neural_scores[cid] = hazard.score

        # Real neuro-symbolic verdicts, per commune, from real production data.
        verdicts = {
            cid: resolve_verdict(cid, neural_scores[cid], snap) for cid, snap in snapshots.items()
        }

        # Four-arm comparison, same real snapshots.
        arm_results = {
            cid: run_all_arms(cid, neural_scores[cid], snap) for cid, snap in snapshots.items()
        }

        coverage = rule_coverage(list(snapshots.values()), CATALOG)

    n = len(snapshots)
    n_vetoed = sum(1 for v in verdicts.values() if v.derivation.get("vetoed"))
    n_disagree = sum(1 for arms in arm_results.values() if arms_disagree(arms))
    n_no_rain_signal = sum(1 for s in snapshots.values() if not s.has_trigger_signal)
    n_terrain_populated = sum(1 for s in snapshots.values() if s.slope_p90_deg is not None)
    n_frozen_rain = sum(1 for s in snapshots.values() if "frozen_signal" in s.quality_flags)

    per_commune = []
    for commune in COMMUNES:
        cid = commune.id
        if cid not in verdicts:
            continue
        v = verdicts[cid]
        arms = arm_results[cid]
        per_commune.append(
            {
                "commune_id": cid,
                "nombre": commune.nombre,
                "neural_score": neural_scores[cid],
                "levels_by_arm": {arm: arms[arm].level for arm in ARMS},
                "fired_rules": [r["id"] for r in v.derivation.get("fired_rules", [])],
                "vetoed": v.derivation.get("vetoed", False),
                "confidence": v.confidence,
                "priority": v.priority,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "single-point-in-time spot-check against real production Supabase data; "
        "NOT a repeated measurement, NOT a backtest (no real historical event labels exist)",
        "n_communes": n,
        "n_vetoed": n_vetoed,
        "pct_vetoed": round(n_vetoed / n, 4) if n else 0.0,
        "n_arms_disagree": n_disagree,
        "pct_arms_disagree": round(n_disagree / n, 4) if n else 0.0,
        "n_no_rain_or_seismic_signal": n_no_rain_signal,
        "n_terrain_populated": n_terrain_populated,
        "n_frozen_rain_signal": n_frozen_rain,
        "rule_coverage": {
            "pct_any_fired": coverage.pct_snapshots_with_any_fired_rule,
            "fire_rate_by_rule": coverage.fire_rate_by_rule,
            "evaluable_rate_by_rule": coverage.evaluable_rate_by_rule,
        },
        "per_commune": per_commune,
    }


def _print_report(results: dict[str, Any]) -> None:
    print(f"Generated at: {results['generated_at']}")
    print(f"Communes with real hazard data: {results['n_communes']}")
    print(
        f"Vetoed (no trigger signal at all): {results['n_vetoed']}/{results['n_communes']} "
        f"({results['pct_vetoed'] * 100:.1f}%)"
    )
    print(
        f"Arms disagree (ml_only vs neurosymbolic): {results['n_arms_disagree']}/"
        f"{results['n_communes']} ({results['pct_arms_disagree'] * 100:.1f}%)"
    )
    print(
        f"Communes with terrain (slope) data populated: {results['n_terrain_populated']}/{results['n_communes']}"
    )
    print(
        f"Communes with a frozen rain signal (audit's 2026-07-29 bug, live today): {results['n_frozen_rain_signal']}/{results['n_communes']}"
    )
    print("\nRule coverage (real data):")
    for rule_id, rate in results["rule_coverage"]["fire_rate_by_rule"].items():
        evaluable = results["rule_coverage"]["evaluable_rate_by_rule"][rule_id]
        print(f"  {rule_id}: fire={rate:.2f} evaluable={evaluable:.2f}")

    print("\nPer-commune (real):")
    print(
        f"{'ID':<4}{'Nombre':<24}{'neural':>8}  {'ml_only':<10}{'neurosym':<10}{'vetoed':<8}{'conf':>6}"
    )
    for row in results["per_commune"]:
        score = f"{row['neural_score']:.3f}" if row["neural_score"] is not None else "  n/a"
        print(
            f"{row['commune_id']:<4}{row['nombre']:<24}{score:>8}  "
            f"{row['levels_by_arm']['ml_only']:<10}{row['levels_by_arm']['neurosymbolic']:<10}"
            f"{str(row['vetoed']):<8}{row['confidence']:>6.2f}"
        )


async def main_async(json_out: Path | None) -> None:
    results = await collect_real_results()
    _print_report(results)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {json_out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(main_async(args.json_out))


if __name__ == "__main__":
    main()
