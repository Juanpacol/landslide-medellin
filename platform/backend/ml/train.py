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

from db.models.landslide_event import LandslideEvent  # noqa: E402
from db.models.ml_feature import MLFeature  # noqa: E402
from db.session import SyncSessionLocal, sync_engine  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
METRICS_PATH = MODELS_DIR / "metrics.json"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"
# Resultado de la ÚLTIMA corrida (exitosa o no). metrics.json en cambio solo
# se escribe cuando el entrenamiento completa: siempre describe al
# best_model.pkl vigente, nunca a una corrida abortada.
LAST_ATTEMPT_PATH = MODELS_DIR / "last_train_attempt.json"


def _write_attempt(payload: dict[str, Any]) -> None:
    LAST_ATTEMPT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _provenance() -> dict[str, Any]:
    """Sello de procedencia para metrics.json: permite detectar drift entre
    artefactos (¿este metrics.json corresponde a este best_model.pkl?)."""
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
    except Exception:  # noqa: BLE001 — sin .git (p.ej. imagen Docker) no es error
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
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return str(int(digits))
    return text


def _load_events_index(session: Session) -> dict[str, list[date]]:
    """Índice (commune_id → fechas) de eventos REALES. Los sintéticos
    (is_synthetic=true, generados con Snake Line) se excluyen: entrenar con
    ellos y validar con la misma heurística sería contaminación circular."""
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


def _collect_all_numeric_keys(session: Session, communes: list[str]) -> set[str]:
    """Detecta TODAS las claves numéricas presentes en MLFeature.features
    (incluyendo sismos, API) para forzar que entren al modelo."""
    all_keys: set[str] = {"centroid_lat", "centroid_lon", "precip_acum_7d", "n_events_window"}
    rows = session.scalars(select(MLFeature)).all()
    for row in rows:
        if row.features:
            for k, v in row.features.items():
                if k not in ["source", "nombre", "official_codigo", "station_codes", "barrios"]:
                    try:
                        float(str(v).replace(",", "."))
                        all_keys.add(k)
                    except (ValueError, TypeError):
                        pass
    return all_keys


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
        if r.commune_id == commune_id and r.reference_date is not None and r.reference_date <= cutoff
    ]
    out.sort(key=lambda r: (r.reference_date or datetime.min.replace(tzinfo=timezone.utc), r.id), reverse=True)
    return out


def _build_supervised_matrix(
    session: Session,
) -> tuple[np.ndarray, np.ndarray, list[str], list[dict[str, Any]], str]:
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
        return np.zeros((0, 0)), np.array([]), [], [], "future_7d"

    keys = sorted({k for r in raw_rows for k in r.keys()})

    # Force inclusion of new features (sismos, API, amenaza por barrio) even
    # if sparse data. This ensures they train into the model when data
    # becomes available, instead of being silently dropped by the sorted-keys
    # union above if no row happens to have them yet.
    force_keys = {
        "seismic_recent_intensity",
        "antecedent_precip_index",
        "pct_barrios_alta_amenaza",
        "soil_water_index_pct",
        "seismic_x_swi",
    }
    keys = sorted(set(keys) | force_keys)

    matrix = np.zeros((len(raw_rows), len(keys)), dtype=float)
    for i, r in enumerate(raw_rows):
        for j, k in enumerate(keys):
            if k in r:
                matrix[i, j] = r[k]

    col_medians = np.nanmedian(matrix, axis=0)
    inds = np.where(np.isnan(matrix))
    matrix[inds] = np.take(col_medians, inds[1])

    y_future = np.array(targets_future, dtype=int)
    if int(np.sum(y_future)) > 0:
        return matrix, y_future, keys, meta, "future_7d"

    y_past = np.array(targets_past, dtype=int)
    return matrix, y_past, keys, meta, "past_7d_fallback"


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


_MIN_TEMPORAL_POSITIVES = 3  # mínimo de positivos a cada lado del corte


def _temporal_validation(
    model_template: Any,
    Xs: np.ndarray,
    y: np.ndarray,
    meta: list[dict[str, Any]],
) -> dict[str, Any]:
    """AUC entrenando con el pasado y validando con el futuro.

    El CV aleatorio (shuffle) puede sobreestimar: mezcla días vecinos del
    mismo episodio de lluvia entre train y test. Esta métrica corta por fecha
    (percentil 80 de las fechas de los positivos) y responde la pregunta real
    del producto: ¿el modelo anticipa eventos que aún no ha visto?
    Si no hay suficientes positivos a ambos lados, reporta null con motivo.
    """
    from sklearn.base import clone

    days = np.array([m["reference_day"] for m in meta])
    pos_days = sorted(days[y == 1])
    if len(pos_days) < 2 * _MIN_TEMPORAL_POSITIVES:
        return {
            "train_auc_temporal": None,
            "temporal_reason": f"solo {len(pos_days)} positivos; se requieren ≥{2 * _MIN_TEMPORAL_POSITIVES}",
        }

    cutoff = pos_days[int(len(pos_days) * 0.8)]
    train_mask = days < cutoff
    test_mask = ~train_mask
    y_tr, y_te = y[train_mask], y[test_mask]
    if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2 or int(y_te.sum()) < _MIN_TEMPORAL_POSITIVES:
        return {
            "train_auc_temporal": None,
            "temporal_reason": f"corte {cutoff} no deja ambas clases (o <{_MIN_TEMPORAL_POSITIVES} positivos) en test",
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
        X, y, feature_names, meta, target_strategy = _build_supervised_matrix(session)

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
            "target_strategy": target_strategy,
            "feature_names": feature_names,
            "error": "Sin filas válidas con reference_date para entrenar.",
            **provenance,
        }
        _write_attempt(payload)
        return payload

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    Xs = np.nan_to_num(Xs, nan=0.0, posinf=0.0, neginf=0.0)

    if len(np.unique(y)) < 2:
        # Abortar ANTES de persistir scaler/feature_names: si se guardan aquí y
        # el clasificador no se entrena, quedan artefactos inconsistentes con el
        # best_model.pkl anterior (vector de features distinto → predict roto).
        payload = {
            "n_samples": n_samples,
            "n_positive": n_positive,
            "n_features": n_features,
            "best_model": None,
            "cv_mean_auc": None,
            "cv_strategy": None,
            "target_strategy": target_strategy,
            "feature_names": feature_names,
            "error": "La variable objetivo tiene una sola clase; no se entrena clasificador.",
            **provenance,
        }
        _write_attempt(payload)
        return payload

    sm = SMOTE(random_state=42)
    X_res, y_res = sm.fit_resample(Xs, y)

    class_values = np.array([0, 1], dtype=int)
    weights = class_weight.compute_class_weight(class_weight="balanced", classes=class_values, y=y_res)
    class_weight_map = {int(cls): float(w) for cls, w in zip(class_values, weights)}
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
            "error": "Ningún modelo pudo evaluarse con AUC-ROC.",
            **provenance,
        }
        _write_attempt(payload)
        return payload

    best_model.fit(X_res, y_res)

    # Validación temporal: pasado→futuro sobre los datos SIN resamplear.
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

    # Persistir los 4 artefactos JUNTOS y solo tras entrenar con éxito.
    # Si scaler/feature_names se guardaran antes del fit (como pasaba), un
    # fallo a mitad de camino deja artefactos de corridas distintas mezclados
    # → shape mismatch en predict (incidente del 2026-07-07).
    builder = FeatureBuilder(MODELS_DIR)
    builder.save_scaler(scaler)
    builder.save_feature_names(feature_names)
    artifact = {
        "model": best_model,
        "feature_names": feature_names,
        "scaler_fitted": True,
    }
    joblib.dump(artifact, BEST_MODEL_PATH)

    # Benchmark fijo (ml/models/benchmark.json): AUC comparable entre corridas.
    try:
        from ml.benchmark import evaluate_benchmark

        with SyncSessionLocal() as session:
            benchmark = evaluate_benchmark(best_model, scaler, feature_names, session) or {}
    except Exception as exc:  # noqa: BLE001
        benchmark = {"benchmark_auc": None, "reason": f"error: {exc!r}"}

    model_version = "teyva-ml-1.0"
    payload = {
        "n_samples": n_samples,
        "n_positive": n_positive,
        "n_features": n_features,
        "n_samples_after_smote": int(len(y_res)),
        "n_positive_after_smote": int(np.sum(y_res)),
        "best_model": best_name,
        "cv_mean_auc": float(best_auc),
        "cv_strategy": cv_name,
        "target_strategy": target_strategy,
        "train_auc_roc": train_auc,
        "classification_threshold": 0.3,
        "train_precision_at_0_3": train_precision,
        "train_recall_at_0_3": train_recall,
        "class_weight": class_weight_map,
        "feature_names": feature_names,
        "model_version": model_version,
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
