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
    """Id canónico ("1".."21") de un commune_id de la BD.

    Delega en `domain.communes.canonical_id`, que TRADUCE los códigos oficiales
    ("50".."90" de los corregimientos) al espacio canónico. La versión anterior
    normalizaba a mano con `str(int(digits))`, así que un evento guardado con
    `commune_id='70'` (código oficial de Altavista = id 19) quedaba como comuna
    "70": un id que no existe en `domain/communes.py`, que nunca cruzaba con
    ninguna fila de `ml_features` y que por tanto perdía su etiqueta en silencio.
    Con solo 36 eventos geolocalizados, perder uno no es un detalle.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return canonical_id(text) or None


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
    """(X, y, feature_names, meta, target_strategy, feature_coverage)."""
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

    # Se fuerzan las claves declaradas en `ml/feature_registry.py` aunque
    # ninguna fila las traiga todavía: sin esto la unión de claves observadas
    # las descarta en silencio y la feature "existe" en el código pero nunca
    # entrena. Es exactamente lo que le pasó a las 4 de ingeniería (ver el
    # docstring del registro). La deny-list ya se aplicó en
    # `features.py::_numeric_from_json`, así que `keys` no la contiene.
    keys = sorted(set(keys) | set(FORCE_KEYS))

    matrix = np.zeros((len(raw_rows), len(keys)), dtype=float)
    # Cobertura: fracción de filas donde la clave estaba PRESENTE de verdad,
    # frente a rellenada con 0.0 aquí abajo. Es la métrica que juzga un backfill
    # con independencia del AUC: si la cobertura sube y el AUC no se mueve, el
    # backfill igual eliminó un defecto de imputación.
    #
    # OJO con el 0.0: es un valor CRUDO, así que tras escalar queda en ≈−2σ, no
    # en un valor neutro. Para una clave con media grande eso no es "sin dato",
    # es "valor extremadamente bajo" — y según la feature puede equivocarse en la
    # dirección peligrosa. Una clave con cobertura baja es ruido con un
    # desplazamiento de media, no una feature.
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
    if (
        len(np.unique(y_tr)) < 2
        or len(np.unique(y_te)) < 2
        or int(y_te.sum()) < _MIN_TEMPORAL_POSITIVES
    ):
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
        X, y, feature_names, meta, target_strategy, coverage = _build_supervised_matrix(session)

    n_samples = int(X.shape[0])
    n_features = int(X.shape[1]) if n_samples else 0
    n_positive = int(np.sum(y)) if n_samples else 0

    # Se incluye en TODOS los payloads (también los abortados): saber que una
    # clave forzada tiene cobertura 0.0 es justo lo que explica un aborto.
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
            "error": "Sin filas válidas con reference_date para entrenar.",
            **coverage_payload,
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
            **coverage_payload,
            **provenance,
        }
        _write_attempt(payload)
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
            "error": "Ningún modelo pudo evaluarse con AUC-ROC.",
            **coverage_payload,
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

    # Importancias: si una clave forzada sale en ~0 CON buena cobertura, eso es
    # evidencia real de que la señal es débil a granularidad comuna-semana, y
    # vale más escribirla que esconderla.
    importances: dict[str, float] | None = None
    raw_imp = getattr(best_model, "feature_importances_", None)
    if raw_imp is not None and len(raw_imp) == len(feature_names):
        importances = {
            k: round(float(v), 6) for k, v in zip(feature_names, raw_imp, strict=True)
        }

    model_version = "teyva-ml-1.0"
    payload = {
        "n_samples": n_samples,
        "n_positive": n_positive,
        "n_features": n_features,
        "n_samples_after_smote": int(len(y_res)),
        "n_positive_after_smote": int(np.sum(y_res)),
        "best_model": best_name,
        # OJO: `cv_mean_auc` se calcula sobre (X_res, y_res), es decir DESPUÉS
        # de SMOTE, así que puntos sintéticos derivados de un positivo pueden
        # caer en el fold de test junto a su padre. Está inflado por
        # construcción y NO es comparable entre corridas cuyo balance de clases
        # cambia. Para comparar antes/después usar `benchmark_auc` (conjunto de
        # casos congelado) y `train_auc_temporal` (validación pasado→futuro).
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
