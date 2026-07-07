"""
Benchmark fijo de evaluación — detecta regresiones entre reentrenamientos.

Problema que resuelve: sin un conjunto de evaluación ESTABLE, cada
reentrenamiento puede "mejorar" su propia métrica de CV (calculada sobre
datos que cambian corrida a corrida) mientras empeora contra los casos que
importan. Este módulo congela un snapshot de casos
`(commune_id, reference_date, label)` en `ml/models/benchmark.json` y cada
corrida de `ml.train` lo evalúa igual, para que `benchmark_auc` sea
comparable entre versiones del modelo.

Flujo:
- `python -m ml.benchmark --freeze` crea/actualiza el snapshot desde la BD:
  positivos = eventos reales (is_synthetic=false) con commune_id y fecha;
  negativos = muestreo determinista (seed fijo) de días/comunas sin evento
  en ±7 días, tomados de ml_features.
- `evaluate_benchmark(model, scaler, feature_names, session)` (llamado desde
  ml/train.py) reconstruye el vector de features de cada caso con el MISMO
  FeatureBuilder de producción y reporta AUC-ROC sobre el snapshot.

El snapshot NO se regenera en cada train: solo con --freeze explícito.
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

from db.models.landslide_event import LandslideEvent  # noqa: E402
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
    """Congela el snapshot actual de casos en benchmark.json."""
    events = session.scalars(
        select(LandslideEvent).where(LandslideEvent.is_synthetic.is_(False))
    ).all()

    positives: list[dict[str, str]] = []
    event_days: set[tuple[str, date]] = set()
    for ev in events:
        d = _parse_date(ev.fecha)
        if d is None or not ev.commune_id:
            continue
        cid = str(int("".join(ch for ch in str(ev.commune_id) if ch.isdigit()) or 0) or ev.commune_id)
        positives.append({"commune_id": cid, "reference_date": d.isoformat(), "label": "1"})
        event_days.add((cid, d))

    # Candidatos a negativo: días/comunas con features y SIN evento en ±7d.
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
    """AUC del modelo dado contra el snapshot congelado. None si no hay
    snapshot o si no tiene ambas clases (motivo en el dict de retorno)."""
    if not BENCHMARK_PATH.exists():
        return {"benchmark_auc": None, "reason": "sin benchmark.json — correr `python -m ml.benchmark --freeze`"}

    snapshot = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    cases = snapshot.get("cases") or []
    if not cases:
        return {"benchmark_auc": None, "reason": "benchmark.json vacío"}

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
        # Solo historia hasta la fecha del caso (sin fuga del futuro).
        hist = [
            r
            for r in rows_by_commune.get(cid, [])
            if r.reference_date is not None
            and (r.reference_date.astimezone(timezone.utc).date() if r.reference_date.tzinfo else r.reference_date.date()) <= ref_d
        ]
        if not hist:
            continue
        hist.sort(key=lambda r: (r.reference_date, r.id), reverse=True)
        _, raw_aligned = builder.merge_with_median_impute(hist, feature_order=feature_names)
        X_list.append([float(raw_aligned.get(k, 0.0)) for k in feature_names])
        y_list.append(int(case["label"]))

    y = np.array(y_list, dtype=int)
    if len(y) == 0 or len(np.unique(y)) < 2:
        return {"benchmark_auc": None, "reason": "casos evaluables sin ambas clases (gap de cobertura de features)"}

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
    parser.add_argument("--freeze", action="store_true", help="Congelar snapshot desde la BD")
    args = parser.parse_args()

    from db.session import SyncSessionLocal, sync_engine

    _ = sync_engine  # fuerza init de conexión
    if args.freeze:
        with SyncSessionLocal() as session:
            snap = freeze_benchmark(session)
        print(json.dumps({k: snap[k] for k in ("frozen_at", "n_positive", "n_negative")}, indent=2))
    else:
        print("Uso: python -m ml.benchmark --freeze")


if __name__ == "__main__":
    main()
