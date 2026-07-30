"""Real-data spot check, take 2 — using ALTERNATE real sources to bypass the live rainfall
feed's frozen-signal bug (`docs/research/production_validation_2026-07-30.md` §"the most
important finding"), to see whether the geotechnical rules (R-GEO-01/02, R-SEIS-01) can fire at
all when fed genuinely varying, real rain and slope data instead of the corrupted live snapshot.

## Two alternate sources, one usable and one not (checked before using either)

1. **Historical rain via IDEAM** (`ml_features` rows with `source='historical_ideam'`, from
   `scraper/historical_backfill.py`): confirmed usable — real day-to-day variation (0.0, 22.1,
   0.9, 3.9mm...), max 104.4mm/day across 1,685 rows, 583 distinct values. But it ONLY covers 3
   communes (15, 18, 21), and commune 18's data stops in 2020 — too stale to represent "now".
   Communes 15 and 21 have data through 2026-07-04 (26 days before this script's run date) —
   recent enough to be informative, though not live.
2. **Historical rain via SIATA** (`source='historical_siata'`): confirmed NOT usable — max
   92,202 mm/day, the exact corrupted value `docs/research/audit-2026-07.md` documented, still
   present, unfixed. This script does not use it, and says so in its own output rather than
   silently ignoring the column.

Slope is fetched LIVE from Open Topo Data's public SRTM API (no DB write, no key) for all 21
communes' centroids — the same method `scraper/terrain_features.py` uses, reused here directly
rather than reimplemented.

## Safety: read-only + one public API call, same guarantee as validate_against_production.py

No `INSERT`/`UPDATE` anywhere. The only network call beyond Supabase reads is to Open Topo Data's
public SRTM endpoint (already used and verified working earlier this session).

## Usage

    cd platform/backend && export PYTHONPATH=.
    python -m evaluation.validate_with_alternate_sources --json-out /path/to/report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from application.neurosymbolic.infer import resolve_verdict
from db.session import AsyncSessionLocal
from domain.communes import CENTROIDS, COMMUNES
from domain.rules.catalog import CATALOG
from domain.rules.facts import TerritorySnapshot
from evaluation.primary_metrics import rule_coverage
from evaluation.run import ARMS, arms_disagree, run_all_arms
from ml.precip_index import compute_antecedent_precip_index
from ml.soil_water_index import compute_swi
from scraper.terrain_features import SAMPLE_OFFSET_M, _fetch_elevations, _offset_points, _slope_deg_from_elevations

# historical_siata is deliberately excluded — confirmed corrupted (see module docstring).
USABLE_HISTORICAL_SOURCE = "historical_ideam"
# Below this many days of staleness, historical rain data is treated as "current enough to
# inform today's snapshot"; commune 18's data (stale since 2020) is excluded on this basis.
MAX_STALENESS_DAYS = 90


async def _historical_daily_rain(session) -> dict[str, dict[date, float]]:
    """Real daily rain per commune from `ml_features`, `historical_ideam` source only.
    Same query shape as `scraper/validar_eventos_historicos.py::_daily_rain_by_commune`,
    narrowed to the one source confirmed usable."""
    from collections import defaultdict

    from sqlalchemy import select

    from db.models.ml_feature import MLFeature

    stmt = select(MLFeature.commune_id, MLFeature.reference_date, MLFeature.features).where(
        MLFeature.features["source"].astext == USABLE_HISTORICAL_SOURCE
    )
    rows = (await session.execute(stmt)).all()
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for commune_id, ref, feats in rows:
        if ref is None or commune_id is None:
            continue
        d = ref.astimezone(timezone.utc).date() if ref.tzinfo else ref.date()
        precip = feats.get("precip_sum_mm_day") if isinstance(feats, dict) else None
        if precip is None:
            continue
        out[str(commune_id)][d] = out[str(commune_id)].get(d, 0.0) + float(precip)
    return out


def _usable_communes(daily_rain_by_commune: dict[str, dict[date, float]], today: date) -> dict[str, date]:
    """{commune_id: most_recent_date} for communes whose historical_ideam data is recent
    enough (see MAX_STALENESS_DAYS) to inform today's snapshot."""
    out: dict[str, date] = {}
    for cid, daily in daily_rain_by_commune.items():
        if not daily:
            continue
        latest = max(daily.keys())
        if (today - latest).days <= MAX_STALENESS_DAYS:
            out[cid] = latest
    return out


async def _real_slope_for_commune(client: httpx.AsyncClient, commune_id: str) -> float | None:
    centroid = CENTROIDS.get(commune_id)
    if centroid is None:
        return None
    lat, lon = centroid
    points = _offset_points(lat, lon, SAMPLE_OFFSET_M)
    values = await _fetch_elevations(client, list(points.values()))
    per_dir = dict(zip(points.keys(), values, strict=True))
    return _slope_deg_from_elevations(per_dir, SAMPLE_OFFSET_M)


async def collect_results() -> dict[str, Any]:
    from infrastructure.repositories.landslide_events import real_events
    from ml.hazard import hazard_by_commune

    today = datetime.now(timezone.utc).date()

    async with AsyncSessionLocal() as session:
        hazards = await hazard_by_commune(session)
        daily_rain = await _historical_daily_rain(session)
        events = await real_events(session)

    usable = _usable_communes(daily_rain, today)

    from collections import Counter

    prior_counts: Counter[str] = Counter()
    for ev in events:
        if ev.commune_id:
            prior_counts[str(ev.commune_id)] += 1

    # Live SRTM slope for all 21 communes — one public API call per commune's 5 sample points,
    # batched at up to 100 locations/request by _fetch_elevations already.
    async with httpx.AsyncClient(timeout=30.0) as client:
        slopes: dict[str, float | None] = {}
        for commune in COMMUNES:
            # Open Topo Data's free tier rate-limits to ~1 req/sec; a courtesy pause avoids
            # 429s across 21 sequential commune queries.
            await asyncio.sleep(1.1)
            slopes[commune.id] = await _real_slope_for_commune(client, commune.id)

    snapshots: dict[str, TerritorySnapshot] = {}
    neural_scores: dict[str, float | None] = {}
    rain_source_by_commune: dict[str, str] = {}

    for commune in COMMUNES:
        cid = commune.id
        hazard = hazards.get(cid)
        if hazard is None:
            continue

        swi_pct = None
        antecedent_mm = None
        rain_source = "none (no usable historical data; live feed excluded as corrupted)"
        if cid in usable:
            as_of = usable[cid]
            daily = daily_rain[cid]
            swi = compute_swi(daily, as_of, window_days=30)
            api = compute_antecedent_precip_index(daily, as_of, window_days=15)
            swi_pct = swi
            antecedent_mm = api
            rain_source = f"historical_ideam, as_of={as_of.isoformat()} ({(today - as_of).days}d stale)"
        rain_source_by_commune[cid] = rain_source

        snapshots[cid] = TerritorySnapshot(
            commune_id=cid,
            hazard_fraction=hazard.susceptibility_components.get("hazard"),
            slope_p90_deg=slopes.get(cid),
            twi_p90=None,
            ndvi_min=None,
            swi_pct=swi_pct,
            antecedent_mm=antecedent_mm,
            precip_72h_mm=antecedent_mm,
            seismic_intensity=hazard.trigger_components.get("seismic"),
            prior_event_count=prior_counts.get(cid, 0),
            nearest_critical_facility_m=None,
        )
        neural_scores[cid] = hazard.score

    verdicts = {cid: resolve_verdict(cid, neural_scores[cid], snap) for cid, snap in snapshots.items()}
    arm_results = {cid: run_all_arms(cid, neural_scores[cid], snap) for cid, snap in snapshots.items()}
    coverage = rule_coverage(list(snapshots.values()), CATALOG)

    n = len(snapshots)
    n_disagree = sum(1 for arms in arm_results.values() if arms_disagree(arms))
    n_slope_available = sum(1 for s in snapshots.values() if s.slope_p90_deg is not None)
    n_real_rain_available = len(usable)

    per_commune = []
    for commune in COMMUNES:
        cid = commune.id
        if cid not in snapshots:
            continue
        v = verdicts[cid]
        arms = arm_results[cid]
        per_commune.append(
            {
                "commune_id": cid,
                "nombre": commune.nombre,
                "slope_p90_deg": snapshots[cid].slope_p90_deg,
                "rain_source": rain_source_by_commune[cid],
                "swi_pct": snapshots[cid].swi_pct,
                "levels_by_arm": {arm: arms[arm].level for arm in ARMS},
                "fired_rules": [r["id"] for r in v.derivation.get("fired_rules", [])],
                "vetoed": v.derivation.get("vetoed", False),
                "confidence": v.confidence,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "single-point-in-time spot-check using alternate real data sources "
        "(live SRTM slope + historical_ideam rain) instead of the corrupted live rainfall feed",
        "excluded_source": "historical_siata (confirmed corrupted: max 92202mm/day observed, "
        "matches docs/research/audit-2026-07.md unfixed)",
        "n_communes": n,
        "n_slope_available_live_srtm": n_slope_available,
        "n_real_historical_rain_available": n_real_rain_available,
        "communes_with_real_rain": sorted(usable.keys(), key=int),
        "n_arms_disagree": n_disagree,
        "rule_coverage": {
            "pct_any_fired": coverage.pct_snapshots_with_any_fired_rule,
            "fire_rate_by_rule": coverage.fire_rate_by_rule,
            "evaluable_rate_by_rule": coverage.evaluable_rate_by_rule,
        },
        "per_commune": per_commune,
    }


def _print_report(results: dict[str, Any]) -> None:
    print(f"Generated at: {results['generated_at']}")
    print(f"Communes: {results['n_communes']}")
    print(f"Live SRTM slope available: {results['n_slope_available_live_srtm']}/{results['n_communes']}")
    print(
        f"Real (non-corrupted) historical rain available: "
        f"{results['n_real_historical_rain_available']}/{results['n_communes']} "
        f"(communes {results['communes_with_real_rain']})"
    )
    print(f"Excluded: {results['excluded_source']}")
    print(f"Arms disagree: {results['n_arms_disagree']}/{results['n_communes']}")
    print("\nRule coverage:")
    for rule_id, rate in results["rule_coverage"]["fire_rate_by_rule"].items():
        evaluable = results["rule_coverage"]["evaluable_rate_by_rule"][rule_id]
        print(f"  {rule_id}: fire={rate:.2f} evaluable={evaluable:.2f}")
    print("\nPer-commune:")
    for row in results["per_commune"]:
        slope = f"{row['slope_p90_deg']:.1f}°" if row["slope_p90_deg"] is not None else "  n/a"
        swi = f"{row['swi_pct']:.1f}%" if row["swi_pct"] is not None else " n/a"
        print(
            f"{row['commune_id']:<4}{row['nombre']:<24}slope={slope:>7}  swi={swi:>6}  "
            f"rules={row['fired_rules']}  neurosym={row['levels_by_arm']['neurosymbolic']}"
        )


async def main_async(json_out: Path | None) -> None:
    results = await collect_results()
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
