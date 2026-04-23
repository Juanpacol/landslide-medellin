from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import LeaveOneOut, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.models.landslide_event import LandslideEvent  # noqa: E402
from db.models.ml_feature import MLFeature  # noqa: E402
from db.session import SyncSessionLocal, sync_engine  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
METRICS_PATH = MODELS_DIR / "metrics.json"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"


def _ref_to_date(ref: datetime) -> date:
    if ref.tzinfo is not None:
        return ref.astimezone(timezone.utc).date()
    return ref.date()


def _parse_event_date(fecha: str | None) -> date | None:
    if not fecha:
        return None
    try:
        return datetime.fromisoformat(fecha[:10]).date()
    except ValueError:
        return None


def _load_events_index(session: Session) -> dict[str, list[date]]:
    by_commune: dict[str, list[date]] = {}
    rows = session.scalars(select(LandslideEvent)).all()
    for ev in rows:
        if not ev.commune_id:
            continue
        cid = str(ev.commune_id)
        d = _parse_event_date(ev.fecha)
        if d is None:
            continue
        by_commune.setdefault(cid, []).append(d)
    return by_commune


def _target_for_ref_day(
    commune_id: str,
    ref_d: date,
    events_by_commune: dict[str, list[date]],
) -> int:
    end = ref_d + timedelta(days=7)
    for d in events_by_commune.get(commune_id, []):
        if ref_d < d <= end:
            return 1
    return 0


def _rows_until(commune_id: str, cutoff: datetime, all_rows: list[MLFeature]) -> list[MLFeature]:
    out = [
        r
        for r in all_rows
        if r.commune_id == commune_id and r.reference_date is not None and r.reference_date <= cutoff
    ]
    out.sort(key=lambda r: (r.reference_date or datetime.min.replace(tzinfo=timezone.utc), r.id), reverse=True)
    return out


def _build_supervised_matrix(session: Session) -> tuple[np.ndarray, np.ndarray, list[str], list[dict[str, Any]]]:
    events_by_commune = _load_events_index(session)
    ml_rows = list(session.scalars(select(MLFeature)).all())

    by_day: dict[tuple[str, date], list[MLFeature]] = defaultdict(list)
    for row in ml_rows:
        if row.reference_date is None:
            continue
        d = _ref_to_date(row.reference_date)
        by_day[(row.commune_id, d)].append(row)

    builder = FeatureBuilder(MODELS_DIR)

    raw_rows: list[dict[str, float]] = []
    targets: list[int] = []
    meta: list[dict[str, Any]] = []

    for (cid, d), grp in by_day.items():
        cutoff = max(r.reference_date for r in grp if r.reference_date is not None)
        hist = _rows_until(cid, cutoff, ml_rows)
        if not hist:
            continue
        _, raw_aligned = builder.merge_with_median_impute(hist, feature_order=None)
        y = _target_for_ref_day(cid, d, events_by_commune)
        raw_rows.append(dict(raw_aligned))
        targets.append(y)
        meta.append(
            {
                "commune_id": cid,
                "reference_day": d.isoformat(),
                "n_history_rows": len(hist),
            }
        )

    if not raw_rows:
        return np.zeros((0, 0)), np.array([]), [], []

    keys = sorted({k for r in raw_rows for k in r.keys()})
    matrix = np.zeros((len(raw_rows), len(keys)), dtype=float)
    for i, r in enumerate(raw_rows):
        for j, k in enumerate(keys):
            if k in r:
                matrix[i, j] = r[k]

    col_medians = np.nanmedian(matrix, axis=0)
    inds = np.where(np.isnan(matrix))
    matrix[inds] = np.take(col_medians, inds[1])

    return matrix, np.array(targets, dtype=int), keys, meta


def _cv_splitter(y: np.ndarray) -> tuple[Any, str]:
    n = len(y)
    _, counts = np.unique(y, return_counts=True)
    min_class = int(counts.min()) if len(counts) else 0
    if n < 50 or min_class < 5:
        return LeaveOneOut(), "LOO"
    return StratifiedKFold(n_splits=5, shuffle=True, random_state=42), "5-fold"


def _auc_scorer(model: Any, X: np.ndarray, y: np.ndarray, cv: Any) -> float:
    scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")
    return float(np.mean(scores))


def train() -> dict[str, Any]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    with SyncSessionLocal() as session:
        X, y, feature_names, _meta = _build_supervised_matrix(session)

    n_samples = int(X.shape[0])
    n_features = int(X.shape[1]) if n_samples else 0
    n_positive = int(np.sum(y)) if n_samples else 0

    if n_samples == 0 or n_features == 0:
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": None,
            "feature_names": feature_names,
            "error": "Sin filas válidas con reference_date para entrenar.",
        }
        METRICS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    builder = FeatureBuilder(MODELS_DIR)
    builder.save_scaler(scaler)
    builder.save_feature_names(feature_names)

    cv, cv_name = _cv_splitter(y)

    if len(np.unique(y)) < 2:
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "n_features": n_features,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": cv_name,
            "feature_names": feature_names,
            "error": "La variable objetivo tiene una sola clase; no se entrena clasificador.",
        }
        METRICS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    candidates: list[tuple[str, Any]] = [
        (
            "RandomForestClassifier",
            RandomForestClassifier(
                n_estimators=200,
                max_depth=6,
                random_state=42,
                class_weight="balanced_subsample",
            ),
        ),
        (
            "XGBClassifier",
            XGBClassifier(
                n_estimators=120,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=1.0,
                random_state=42,
                eval_metric="logloss",
            ),
        ),
        (
            "GradientBoostingClassifier",
            GradientBoostingClassifier(random_state=42),
        ),
    ]

    best_name: str | None = None
    best_model: Any | None = None
    best_auc = -1.0

    for name, model in candidates:
        try:
            auc = _auc_scorer(model, Xs, y, cv)
        except Exception:  # noqa: BLE001
            auc = float("nan")
        if (not np.isnan(auc)) and auc > best_auc:
            best_auc = auc
            best_name = name
            best_model = model

    if best_model is None or best_name is None:
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "n_features": n_features,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": cv_name,
            "feature_names": feature_names,
            "error": "Ningún modelo pudo evaluarse con AUC-ROC.",
        }
        METRICS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    best_model.fit(Xs, y)

    try:
        train_proba = best_model.predict_proba(Xs)[:, 1]
        train_auc = float(roc_auc_score(y, train_proba))
    except Exception:  # noqa: BLE001
        train_auc = float("nan")

    artifact = {
        "model": best_model,
        "feature_names": feature_names,
        "scaler_fitted": True,
    }
    joblib.dump(artifact, BEST_MODEL_PATH)

    model_version = "teyva-ml-1.0"
    payload = {
        "n_samples": n_samples,
        "n_positive": n_positive,
        "n_features": n_features,
        "best_model": best_name,
        "cv_mean_auc": float(best_auc),
        "cv_strategy": cv_name,
        "train_auc_roc": train_auc,
        "feature_names": feature_names,
        "model_version": model_version,
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def main() -> None:
    _ = sync_engine  # noqa: F841
    out = train()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
