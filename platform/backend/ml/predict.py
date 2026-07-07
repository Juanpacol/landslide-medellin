from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.risk_explanations import generate_risk_explanation  # noqa: E402
from constants import risk_level_from_score  # noqa: E402
from db.models.risk_explanation import RiskExplanation  # noqa: E402
from db.models.risk_prediction import RiskPrediction  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402
from observability.predictions import log_prediction  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"
METRICS_PATH = MODELS_DIR / "metrics.json"


def _load_artifact() -> dict[str, Any] | None:
    if not BEST_MODEL_PATH.exists():
        return None
    data = joblib.load(BEST_MODEL_PATH)
    if not isinstance(data, dict) or "model" not in data:
        return None
    return data


def _load_metrics() -> dict[str, Any]:
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


async def predict_risk(comuna_id: int, db: AsyncSession) -> dict[str, Any]:
    metrics = _load_metrics()
    model_version = str(metrics.get("model_version") or "unknown")

    artifact = _load_artifact()
    if artifact is None:
        return {
            "risk_score": 0.0,
            "risk_level": "bajo",
            "confidence": 0.0,
            "features_used": {},
            "model_version": model_version,
            "error": "Modelo no entrenado (falta best_model.pkl).",
        }

    model = artifact["model"]
    feature_names: list[str] = list(artifact.get("feature_names") or metrics.get("feature_names") or [])

    builder = FeatureBuilder(MODELS_DIR)
    bundle = await builder.build_feature_vector(comuna_id, db, feature_order=feature_names or None, apply_scaler=True)

    order = bundle.get("feature_order") or feature_names
    vec_scaled = bundle.get("vector_scaled")
    features_used: dict[str, Any] = bundle.get("features_used") or {}

    if vec_scaled is None:
        scaler = joblib.load(builder.scaler_path())
        raw = bundle.get("vector_raw") or {}
        x = np.array([[float(raw.get(k, 0.0)) for k in order]], dtype=float)
        vec_scaled = scaler.transform(x)[0].tolist()

    x_row = np.array([vec_scaled], dtype=float)
    proba = model.predict_proba(x_row)[0]
    risk_score = float(proba[1]) if proba.shape[0] > 1 else float(proba[0])
    confidence = float(np.max(proba))

    return {
        "risk_score": risk_score,
        "risk_level": risk_level_from_score(risk_score),
        "confidence": confidence,
        "features_used": features_used,
        "model_version": model_version,
    }


async def predict_all_comunas(db: AsyncSession) -> None:
    metrics = _load_metrics()
    model_version = str(metrics.get("model_version") or "teyva-ml-1.0")

    for cid in range(1, 22):
        out = await predict_risk(cid, db)
        risk_score = float(out.get("risk_score") or 0.0)
        risk_level = str(out.get("risk_level") or "bajo")
        confidence = float(out.get("confidence") or 0.0)
        features_used = out.get("features_used") or {}

        raw_output = {
            "features_used": features_used,
            "confidence": confidence,
            "risk_level": risk_level,
            "error": out.get("error"),
        }

        # Generar explicación (GPT-4 Mini si hay API key, template si no)
        try:
            precip_mm = float(features_used.get("precip_sum_mm_day") or features_used.get("mean_precip_mm_snapshot") or 0.0)
            n_events = int(features_used.get("n_events_window") or 0)
            explanation_text, generated_by, explanation_structured = await generate_risk_explanation(
                commune_id=str(cid),
                risk_score=risk_score,
                risk_category=risk_level,
                precip_acum_mm=precip_mm,
                threshold_mm=35.0,
                n_events_7d=n_events,
                db=db,
            )
        except Exception:
            explanation_text = (
                f"Probabilidad estimada de evento en 7 días: {risk_score:.3f} (nivel {risk_level})."
            )
            generated_by = "template"
            explanation_structured = None

        # Log prediction for observability
        log_prediction(
            commune_id=str(cid),
            risk_score=risk_score,
            risk_category=risk_level,
            confidence=confidence,
            model_version=model_version,
            features_used=features_used,
            explanation_text=explanation_text,
            explanation_by=generated_by,
        )

        db.add(
            RiskPrediction(
                commune_id=str(cid),
                risk_score=risk_score,
                risk_category=risk_level,
                model_version=model_version,
                explanation=explanation_text,
                raw_output=raw_output,
            )
        )
        db.add(
            RiskExplanation(
                commune_id=str(cid),
                risk_score=risk_score,
                risk_category=risk_level,
                explanation=explanation_text,
                explanation_json=explanation_structured,
                generated_by=generated_by,
            )
        )

    await db.commit()

    # Alertas Slack basadas en las predicciones que se acaban de escribir.
    # No deben tumbar la corrida de predicción si el webhook falla.
    try:
        from alerts.slack import check_and_fire_critical_risk_alerts, check_and_fire_yellow_alerts

        await check_and_fire_critical_risk_alerts(db)
        await check_and_fire_yellow_alerts(db)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("Alertas Slack post-predicción fallaron (no crítico)")


async def _run_standalone() -> None:
    async with AsyncSessionLocal() as db:
        await predict_all_comunas(db)


if __name__ == "__main__":
    asyncio.run(_run_standalone())
