"""XGBoost estimator — wraps the classifier's output into the `Signal` shape,
without duplicating its I/O-heavy inference (loading `best_model.pkl`,
building the feature vector via `FeatureBuilder`, which needs a DB session
— see `ml/predict.py::predict_risk`, the single owner of that path).

Unlike `rainfall_estimator`/`seismic_estimator`/`terrain_estimator`, which
are pure functions over a `TerritorySnapshot`, the classifier cannot be:
building its feature vector needs an `AsyncSession` and `ml/predict.py`
already owns that call. `estimate_from_prediction()` is a pure *adapter* —
it takes the already-computed `(risk_score, confidence)` `ml/predict.py`
returns and standardizes it into a `Signal`, so callers that compare
signals across sources (e.g. `evaluation/run.py`) don't need a special
case for the classifier.

Uncertainty here is `1 - confidence`: `predict_proba`'s max class
probability is the closest thing the classifier has to a confidence
signal, even though — per docs/research/audit-2026-07.md — it was fit
against contaminated labels and should not be read as calibrated.
"""

from __future__ import annotations

from ml.estimators.base import Signal


def estimate_from_prediction(risk_score: float | None, confidence: float | None) -> Signal:
    if risk_score is None:
        return Signal(value=None, uncertainty=1.0, source="xgboost", coverage=0.0)
    uncertainty = round(1.0 - confidence, 4) if confidence is not None else 1.0
    return Signal(
        value=round(max(0.0, min(1.0, risk_score)), 4),
        uncertainty=uncertainty,
        source="xgboost",
        coverage=1.0,
    )
