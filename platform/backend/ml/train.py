from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import LeaveOneOut, StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.utils import class_weight
from sqlalchemy import select
from sqlalchemy.orm import Session
from xgboost import XGBClassifier

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.models.ml_feature import MLFeature  # noqa: E402
from db.session import SyncSessionLocal, sync_engine  # noqa: E402
from domain.communes import canonical_id  # noqa: E402
from ml.feature_registry import FORCE_KEYS  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
METRICS_PATH = MODELS_DIR / "metrics.json"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"
# Result of the LAST run (successful or not). metrics.json, in contrast, is
# only written when training completes: it always describes the current
# best_model.pkl, never an aborted run.
LAST_ATTEMPT_PATH = MODELS_DIR / "last_train_attempt.json"


def _write_attempt(payload: dict[str, Any]) -> None:
    LAST_ATTEMPT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _alert_label_collapse(n_samples: int, n_positive: int) -> None:
    """Slack alert when training aborts because the positive class collapsed to <2 unique
    values in `y` — the exact silent failure the audit documented
    (docs/research/audit-2026-07.md §3): the `is_synthetic` filter was applied correctly,
    positives disappeared, and nothing notified anyone. `train.py`'s artifact governance
    already protects production (an aborted run never overwrites `best_model.pkl`), but
    protecting production silently is not the same as someone finding out.

    Posts directly via `requests`, independent of the DB-backed alert pipeline in
    `alerts/slack.py` (which needs an AsyncSession this sync script doesn't have) — same
    "notify even if something else is broken" philosophy as
    `.github/actions/notify-failure`. Best-effort: a failed notification must never fail
    the training run itself.
    """
    import os

    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return
    try:
        import requests

        requests.post(
            webhook_url,
            json={
                "text": (
                    ":rotating_light: TEYVA ml.train: entrenamiento abortado — la clase "
                    "positiva colapsó "
                    f"(n_samples={n_samples}, n_positive={n_positive}). "
                    "best_model.pkl NO se sobrescribió. Ver last_train_attempt.json."
                )
            },
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        pass


def _provenance() -> dict[str, Any]:
    """Provenance stamp for metrics.json: lets you detect drift between
    artifacts (does this metrics.json correspond to this best_model.pkl?)."""
    import subprocess

    sha: str | None = None
    try:
        sha = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=BACKEND_ROOT,
            ).stdout.strip()
            or None
        )
    except Exception:  # noqa: BLE001 — no .git (e.g. Docker image) isn't an error
        sha = None
    return {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "git_commit_sha": sha,
    }


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


def _normalize_commune_id(value: Any) -> str | None:
    """Canonical id ("1".."21") from a DB commune_id.

    Delegates to `domain.communes.canonical_id`, which TRANSLATES official
    codes ("50".."90" for corregimientos) into canonical space. The
    previous version normalized by hand with `str(int(digits))`, so an
    event stored with `commune_id='70'` (Altavista's official code = id 19)
    stayed as commune "70": an id that doesn't exist in
    `domain/communes.py`, that never joined with any `ml_features` row, and
    that therefore silently lost its label. With only 36 geolocated
    events, losing one is not a detail.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return canonical_id(text) or None


def _load_events_index(session: Session) -> dict[str, list[date]]:
    """Index (commune_id → dates) of REAL events. Synthetic ones
    (is_synthetic=true, generated with Snake Line) are excluded: training
    with them and validating against the same heuristic would be circular
    contamination."""
    from infrastructure.repositories.landslide_events import real_events_sync

    by_commune: dict[str, list[date]] = {}
    for ev in real_events_sync(session):
        cid = _normalize_commune_id(ev.commune_id)
        if cid is None:
            continue
        d = _parse_event_date(ev.fecha)
        if d is None:
            continue
        by_commune.setdefault(cid, []).append(d)
    return by_commune


def _target_for_ref_day_future(
    commune_id: str,
    ref_d: date,
    events_by_commune: dict[str, list[date]],
) -> int:
    end = ref_d + timedelta(days=7)
    for d in events_by_commune.get(commune_id, []):
        if ref_d < d <= end:
            return 1
    return 0


def _target_for_ref_day_past(
    commune_id: str,
    ref_d: date,
    events_by_commune: dict[str, list[date]],
) -> int:
    start = ref_d - timedelta(days=7)
    for d in events_by_commune.get(commune_id, []):
        if start <= d <= ref_d:
            return 1
    return 0


def _rows_until(commune_id: str, cutoff: datetime, all_rows: list[MLFeature]) -> list[MLFeature]:
    out = [
        r
        for r in all_rows
        if r.commune_id == commune_id
        and r.reference_date is not None
        and r.reference_date <= cutoff
    ]
    out.sort(
        key=lambda r: (r.reference_date or datetime.min.replace(tzinfo=timezone.utc), r.id),
        reverse=True,
    )
    return out


def _build_supervised_matrix(
    session: Session,
) -> tuple[np.ndarray, np.ndarray, list[str], list[dict[str, Any]], str, dict[str, float]]:
    """Returns (X, y, feature_names, meta, target_strategy, feature_coverage)."""
    events_by_commune = _load_events_index(session)
    ml_rows = list(session.scalars(select(MLFeature)).all())

    by_day: dict[tuple[str, date], list[MLFeature]] = defaultdict(list)
    for row in ml_rows:
        if row.reference_date is None:
            continue
        cid = _normalize_commune_id(row.commune_id)
        if cid is None:
            continue
        d = _ref_to_date(row.reference_date)
        by_day[(cid, d)].append(row)

    builder = FeatureBuilder(MODELS_DIR)

    raw_rows: list[dict[str, float]] = []
    targets_future: list[int] = []
    targets_past: list[int] = []
    meta: list[dict[str, Any]] = []

    for (cid, d), grp in by_day.items():
        cutoff = max(r.reference_date for r in grp if r.reference_date is not None)
        hist = _rows_until(cid, cutoff, ml_rows)
        if not hist:
            continue
        _, raw_aligned = builder.merge_with_median_impute(hist, feature_order=None)
        y_future = _target_for_ref_day_future(cid, d, events_by_commune)
        y_past = _target_for_ref_day_past(cid, d, events_by_commune)
        raw_rows.append(dict(raw_aligned))
        targets_future.append(y_future)
        targets_past.append(y_past)
        meta.append(
            {
                "commune_id": cid,
                "reference_day": d.isoformat(),
                "n_history_rows": len(hist),
            }
        )

    if not raw_rows:
        return np.zeros((0, 0)), np.array([]), [], [], "future_7d", {}

    keys = sorted({k for r in raw_rows for k in r.keys()})

    # Keys declared in `ml/feature_registry.py` are forced in even if no row
    # has them yet: without this, the union of observed keys silently drops
    # them and the feature "exists" in code but never trains. That's
    # exactly what happened to the 4 engineered ones (see the registry's
    # docstring). The deny-list was already applied in
    # `features.py::_numeric_from_json`, so `keys` doesn't contain it.
    keys = sorted(set(keys) | set(FORCE_KEYS))

    matrix = np.zeros((len(raw_rows), len(keys)), dtype=float)
    # Coverage: fraction of rows where the key was ACTUALLY present, versus
    # filled with 0.0 below. This is the metric that judges a backfill
    # independent of AUC: if coverage goes up and AUC doesn't move, the
    # backfill still removed an imputation defect.
    #
    # WATCH OUT for the 0.0: it's a RAW value, so after scaling it lands at
    # ≈−2σ, not a neutral value. For a key with a large mean that isn't "no
    # data", it's "extremely low value" — and depending on the feature it can
    # be wrong in the dangerous direction. A low-coverage key is noise with
    # a mean shift, not a feature.
    present_counts: dict[str, int] = dict.fromkeys(keys, 0)
    for i, r in enumerate(raw_rows):
        for j, k in enumerate(keys):
            if k in r:
                matrix[i, j] = r[k]
                present_counts[k] += 1

    n_rows = len(raw_rows)
    coverage = {k: round(present_counts[k] / n_rows, 4) for k in keys} if n_rows else {}

    col_medians = np.nanmedian(matrix, axis=0)
    inds = np.where(np.isnan(matrix))
    matrix[inds] = np.take(col_medians, inds[1])

    y_future = np.array(targets_future, dtype=int)
    if int(np.sum(y_future)) > 0:
        return matrix, y_future, keys, meta, "future_7d", coverage

    y_past = np.array(targets_past, dtype=int)
    return matrix, y_past, keys, meta, "past_7d_fallback", coverage


def _cv_splitter(y: np.ndarray) -> tuple[Any, str]:
    n = len(y)
    _, counts = np.unique(y, return_counts=True)
    min_class = int(counts.min()) if len(counts) else 0
    if n < 50 or min_class < 5:
        return LeaveOneOut(), "LOO"
    return StratifiedKFold(n_splits=5, shuffle=True, random_state=42), "5-fold"


def _auc_scorer(model: Any, X: np.ndarray, y: np.ndarray, cv: Any) -> float:
    if isinstance(cv, LeaveOneOut):
        proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba", n_jobs=1)
        return float(roc_auc_score(y, proba[:, 1]))
    scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc", n_jobs=1)
    return float(np.mean(scores))


_MIN_TEMPORAL_POSITIVES = 3  # minimum positives on each side of the cutoff


def _temporal_validation(
    model_template: Any,
    Xs: np.ndarray,
    y: np.ndarray,
    meta: list[dict[str, Any]],
) -> dict[str, Any]:
    """AUC training on the past and validating on the future.

    Random (shuffled) CV can overestimate: it mixes neighboring days from
    the same rain episode between train and test. This metric cuts by date
    (80th percentile of positive dates) and answers the real product
    question: does the model anticipate events it hasn't seen yet?
    If there aren't enough positives on both sides, it reports null with a
    reason.
    """
    from sklearn.base import clone

    days = np.array([m["reference_day"] for m in meta])
    pos_days = sorted(days[y == 1])
    if len(pos_days) < 2 * _MIN_TEMPORAL_POSITIVES:
        return {
            "train_auc_temporal": None,
            "temporal_reason": f"only {len(pos_days)} positives; ≥{2 * _MIN_TEMPORAL_POSITIVES} required",
        }

    cutoff = pos_days[int(len(pos_days) * 0.8)]
    train_mask = days < cutoff
    test_mask = ~train_mask
    y_tr, y_te = y[train_mask], y[test_mask]
    if (
        len(np.unique(y_tr)) < 2
        or len(np.unique(y_te)) < 2
        or int(y_te.sum()) < _MIN_TEMPORAL_POSITIVES
    ):
        return {
            "train_auc_temporal": None,
            "temporal_reason": f"cutoff {cutoff} leaves test without both classes (or <{_MIN_TEMPORAL_POSITIVES} positives)",
        }

    try:
        model = clone(model_template)
        X_tr, y_tr_res = SMOTE(random_state=42).fit_resample(Xs[train_mask], y_tr)
        model.fit(X_tr, y_tr_res)
        proba = model.predict_proba(Xs[test_mask])[:, 1]
        return {
            "train_auc_temporal": float(roc_auc_score(y_te, proba)),
            "temporal_cutoff": cutoff,
            "temporal_n_test": int(test_mask.sum()),
            "temporal_n_test_positive": int(y_te.sum()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"train_auc_temporal": None, "temporal_reason": f"error: {exc!r}"}


def train() -> dict[str, Any]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    provenance = _provenance()

    with SyncSessionLocal() as session:
        X, y, feature_names, meta, target_strategy, coverage = _build_supervised_matrix(session)

    n_samples = int(X.shape[0])
    n_features = int(X.shape[1]) if n_samples else 0
    n_positive = int(np.sum(y)) if n_samples else 0

    # Included in ALL payloads (aborted ones too): knowing a forced key has
    # 0.0 coverage is exactly what explains an abort.
    coverage_payload: dict[str, Any] = {
        "feature_coverage": coverage,
        "feature_coverage_min": (
            round(min((coverage[k] for k in feature_names if k in coverage), default=0.0), 4)
            if feature_names
            else None
        ),
    }

    if n_samples == 0 or n_features == 0:
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": None,
            "target_strategy": target_strategy,
            "feature_names": feature_names,
            "error": "No valid rows with reference_date to train on.",
            **coverage_payload,
            **provenance,
        }
        _write_attempt(payload)
        return payload

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    Xs = np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)

    if len(np.unique(y)) < 2:
        # Abort BEFORE persisting scaler/feature_names: if they were saved
        # here and the classifier doesn't train, the artifacts end up
        # inconsistent with the previous best_model.pkl (different feature
        # vector → broken predict).
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "n_features": n_features,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": None,
            "target_strategy": target_strategy,
            "feature_names": feature_names,
            "error": "The target variable has a single class; no classifier trained.",
            **coverage_payload,
            **provenance,
        }
        _write_attempt(payload)
        _alert_label_collapse(n_samples, n_positive)
        return payload

    sm = SMOTE(random_state=42)
    X_res, y_res = sm.fit_resample(Xs, y)

    class_values = np.array([0, 1], dtype=int)
    weights = class_weight.compute_class_weight(
        class_weight="balanced", classes=class_values, y=y_res
    )
    class_weight_map = {int(cls): float(w) for cls, w in zip(class_values, weights, strict=False)}
    scale_pos_weight = class_weight_map[1] / max(class_weight_map[0], 1e-9)

    cv, cv_name = _cv_splitter(y_res)
    small_n = len(y_res) < 50

    rf_trees = 80 if small_n else 200
    xgb_trees = 60 if small_n else 120

    candidates: list[tuple[str, Any]] = [
        (
            "RandomForestClassifier",
            RandomForestClassifier(
                n_estimators=rf_trees,
                max_depth=6,
                random_state=42,
                class_weight=class_weight_map,
                n_jobs=1,
            ),
        ),
        (
            "XGBClassifier",
            XGBClassifier(
                n_estimators=xgb_trees,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=1.0,
                random_state=42,
                eval_metric="logloss",
                scale_pos_weight=scale_pos_weight,
                n_jobs=1,
            ),
        ),
        (
            "LogisticRegression",
            LogisticRegression(
                random_state=42,
                max_iter=2000,
                class_weight=class_weight_map,
            ),
        ),
    ]

    best_name: str | None = None
    best_model: Any | None = None
    best_auc = -1.0

    for name, model in candidates:
        try:
            auc = _auc_scorer(model, X_res, y_res, cv)
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
            "target_strategy": target_strategy,
            "feature_names": feature_names,
            "error": "No model could be evaluated with AUC-ROC.",
            **coverage_payload,
            **provenance,
        }
        _write_attempt(payload)
        return payload

    best_model.fit(X_res, y_res)

    # Temporal validation: past→future on the data WITHOUT resampling.
    temporal = _temporal_validation(best_model, Xs, y, meta)

    try:
        train_proba = best_model.predict_proba(X_res)[:, 1]
        train_auc = float(roc_auc_score(y_res, train_proba))
        y_pred = (train_proba >= 0.3).astype(int)
        train_precision = float(precision_score(y_res, y_pred, zero_division=0))
        train_recall = float(recall_score(y_res, y_pred, zero_division=0))
    except Exception:  # noqa: BLE001
        train_auc = float("nan")
        train_precision = float("nan")
        train_recall = float("nan")

    # Persist the 4 artifacts TOGETHER, only after training succeeds. If
    # scaler/feature_names were saved before the fit (as they used to be),
    # a mid-way failure leaves artifacts from different runs mixed together
    # → shape mismatch at predict time (the 2026-07-07 incident).
    builder = FeatureBuilder(MODELS_DIR)
    builder.save_scaler(scaler)
    builder.save_feature_names(feature_names)
    artifact = {
        "model": best_model,
        "feature_names": feature_names,
        "scaler_fitted": True,
    }
    joblib.dump(artifact, BEST_MODEL_PATH)

    # Fixed benchmark (ml/models/benchmark.json): AUC comparable across runs.
    try:
        from ml.benchmark import evaluate_benchmark

        with SyncSessionLocal() as session:
            benchmark = evaluate_benchmark(best_model, scaler, feature_names, session) or {}
    except Exception as exc:  # noqa: BLE001
        benchmark = {"benchmark_auc": None, "reason": f"error: {exc!r}"}

    # Importances: if a forced key comes out at ~0 WITH good coverage, that's
    # real evidence the signal is weak at commune-week granularity, and it's
    # worth writing that down rather than hiding it.
    importances: dict[str, float] | None = None
    raw_imp = getattr(best_model, "feature_importances_", None)
    if raw_imp is not None and len(raw_imp) == len(feature_names):
        importances = {k: round(float(v), 6) for k, v in zip(feature_names, raw_imp, strict=True)}

    model_version = "teyva-ml-1.0"
    payload = {
        "n_samples": n_samples,
        "n_positive": n_positive,
        "n_features": n_features,
        "n_samples_after_smote": int(len(y_res)),
        "n_positive_after_smote": int(np.sum(y_res)),
        "best_model": best_name,
        # WATCH OUT: `cv_mean_auc` is computed on (X_res, y_res), i.e. AFTER
        # SMOTE, so synthetic points derived from a positive can land in the
        # test fold alongside their parent. It's inflated by construction
        # and NOT comparable across runs whose class balance changes. To
        # compare before/after use `benchmark_auc` (frozen case set) and
        # `train_auc_temporal` (past→future validation).
        "cv_mean_auc": float(best_auc),
        "cv_strategy": cv_name,
        "target_strategy": target_strategy,
        "train_auc_roc": train_auc,
        "classification_threshold": 0.3,
        "train_precision_at_0_3": train_precision,
        "train_recall_at_0_3": train_recall,
        "class_weight": class_weight_map,
        "feature_names": feature_names,
        "feature_importances": importances,
        "model_version": model_version,
        **coverage_payload,
        **temporal,
        **benchmark,
        **provenance,
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_attempt(payload)
    return payload


def main() -> None:
    _ = sync_engine  # noqa: F841
    from application.train_model import run_training

    out = run_training()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    from observability.logging_config import configure_logging

    configure_logging("ml-train")
    main()
