"""
Fixed evaluation benchmark — detects regressions across retrains.

Problem this solves: without a STABLE evaluation set, every retrain can
"improve" its own CV metric (computed on data that changes run to run)
while getting worse on the cases that matter. This module freezes a
snapshot of cases `(commune_id, reference_date, label)` in
`ml/models/benchmark.json`, and every `ml.train` run evaluates against the
same one, so `benchmark_auc` is comparable across model versions.

Flow:
- `python -m ml.benchmark --freeze` creates/updates the snapshot from the
  DB: positives = real events (is_synthetic=false) with commune_id and
  date; negatives = deterministic sampling (fixed seed) of days/communes
  with no event within ±7 days, taken from ml_features.
- `evaluate_benchmark(model, scaler, feature_names, session)` (called from
  ml/train.py) rebuilds each case's feature vector with the SAME
  production FeatureBuilder and reports AUC-ROC over the snapshot.

The snapshot is NOT regenerated on every train run: only with explicit
--freeze.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.models.ml_feature import MLFeature  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
BENCHMARK_PATH = MODELS_DIR / "benchmark.json"

_SEED = 42
_NEGATIVES_PER_POSITIVE = 5
_EVENT_WINDOW_DAYS = 7


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:10]).date()
    except ValueError:
        return None


def freeze_benchmark(session: Session) -> dict[str, Any]:
    """Freezes the current snapshot of cases into benchmark.json."""
    from infrastructure.repositories.landslide_events import real_events_sync

    events = real_events_sync(session)

    positives: list[dict[str, str]] = []
    event_days: set[tuple[str, date]] = set()
    for ev in events:
        d = _parse_date(ev.fecha)
        if d is None or not ev.commune_id:
            continue
        cid = str(
            int("".join(ch for ch in str(ev.commune_id) if ch.isdigit()) or 0) or ev.commune_id
        )
        positives.append({"commune_id": cid, "reference_date": d.isoformat(), "label": "1"})
        event_days.add((cid, d))

    # Negative candidates: days/communes with features and NO event within ±7d.
    ml_rows = session.scalars(select(MLFeature).where(MLFeature.reference_date.isnot(None))).all()
    candidates: list[tuple[str, date]] = []
    seen: set[tuple[str, date]] = set()
    for row in ml_rows:
        cid = str(row.commune_id)
        d = row.reference_date
        d = d.astimezone(timezone.utc).date() if d.tzinfo else d.date()
        if (cid, d) in seen:
            continue
        seen.add((cid, d))
        near_event = any(
            (cid, d + timedelta(days=off)) in event_days
            for off in range(-_EVENT_WINDOW_DAYS, _EVENT_WINDOW_DAYS + 1)
        )
        if not near_event:
            candidates.append((cid, d))

    rng = random.Random(_SEED)
    n_neg = min(len(candidates), max(len(positives) * _NEGATIVES_PER_POSITIVE, 50))
    negatives = [
        {"commune_id": cid, "reference_date": d.isoformat(), "label": "0"}
        for cid, d in sorted(rng.sample(candidates, n_neg))
    ]

    snapshot = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "seed": _SEED,
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "cases": positives + negatives,
    }
    BENCHMARK_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot


def evaluate_benchmark(
    model: Any,
    scaler: Any,
    feature_names: list[str],
    session: Session,
) -> dict[str, Any] | None:
    """Given model's AUC against the frozen snapshot. None if there's no
    snapshot or it doesn't have both classes (reason in the return dict)."""
    if not BENCHMARK_PATH.exists():
        return {
            "benchmark_auc": None,
            "reason": "no benchmark.json — run `python -m ml.benchmark --freeze`",
        }

    snapshot = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    cases = snapshot.get("cases") or []
    if not cases:
        return {"benchmark_auc": None, "reason": "benchmark.json is empty"}

    builder = FeatureBuilder(MODELS_DIR)
    all_rows = session.scalars(select(MLFeature)).all()
    rows_by_commune: dict[str, list[MLFeature]] = {}
    for r in all_rows:
        rows_by_commune.setdefault(str(r.commune_id), []).append(r)

    X_list: list[list[float]] = []
    y_list: list[int] = []
    for case in cases:
        cid = case["commune_id"]
        ref_d = _parse_date(case["reference_date"])
        if ref_d is None:
            continue
        # Only history up to the case's date (no future leakage).
        hist = [
            r
            for r in rows_by_commune.get(cid, [])
            if r.reference_date is not None
            and (
                r.reference_date.astimezone(timezone.utc).date()
                if r.reference_date.tzinfo
                else r.reference_date.date()
            )
            <= ref_d
        ]
        if not hist:
            continue
        hist.sort(key=lambda r: (r.reference_date, r.id), reverse=True)
        _, raw_aligned = builder.merge_with_median_impute(hist, feature_order=feature_names)
        X_list.append([float(raw_aligned.get(k, 0.0)) for k in feature_names])
        y_list.append(int(case["label"]))

    y = np.array(y_list, dtype=int)
    if len(y) == 0 or len(np.unique(y)) < 2:
        return {
            "benchmark_auc": None,
            "reason": "evaluable cases missing one class (feature coverage gap)",
        }

    from sklearn.metrics import roc_auc_score

    X = scaler.transform(np.array(X_list, dtype=float))
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    proba = model.predict_proba(X)[:, 1]
    return {
        "benchmark_auc": float(roc_auc_score(y, proba)),
        "benchmark_n_cases": int(len(y)),
        "benchmark_n_positive": int(y.sum()),
        "benchmark_frozen_at": snapshot.get("frozen_at"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true", help="Freeze snapshot from the DB")
    args = parser.parse_args()

    from db.session import SyncSessionLocal, sync_engine

    _ = sync_engine  # forces connection init
    if args.freeze:
        with SyncSessionLocal() as session:
            snap = freeze_benchmark(session)
        print(json.dumps({k: snap[k] for k in ("frozen_at", "n_positive", "n_negative")}, indent=2))
    else:
        print("Usage: python -m ml.benchmark --freeze")


if __name__ == "__main__":
    main()
