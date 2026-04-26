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

from db.models.risk_prediction import RiskPrediction  # noqa: E402
from db.session import AsyncSessionLocal  # noqa: E402
from ml.features import FeatureBuilder  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"
METRICS_PATH = MODELS_DIR / "metrics.json"


def _risk_level_from_score(score: float) -> str:
    if score < 0.3:
        return "bajo"
    if score < 0.6:
        return "medio"
    if score < 0.8:
        return "alto"
    return "critico"


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
        "risk_level": _risk_level_from_score(risk_score),
        "confidence": confidence,
        "features_used": features_used,
        "model_version": model_version,
    }


async def predict_all_comunas(db: AsyncSession) -> None:
    metrics = _load_metrics()
    model_version = str(metrics.get("model_version") or "teyva-ml-1.0")

    for cid in range(1, 22):
        out = await predict_risk(cid, db)
        raw_output = {
            "features_used": out.get("features_used"),
            "confidence": out.get("confidence"),
            "risk_level": out.get("risk_level"),
            "error": out.get("error"),
        }
        explanation = (
            f"Probabilidad estimada de evento DAGRD en 7 días: {out.get('risk_score', 0.0):.3f} "
            f"(nivel {out.get('risk_level')})."
        )
        db.add(
            RiskPrediction(
                commune_id=str(cid),
                risk_score=float(out.get("risk_score") or 0.0),
                risk_category=str(out.get("risk_level") or "bajo"),
                model_version=model_version,
                explanation=explanation,
                raw_output=raw_output,
            )
        )
    await db.commit()


async def _run_standalone() -> None:
    async with AsyncSessionLocal() as db:
        await predict_all_comunas(db)


if __name__ == "__main__":
    asyncio.run(_run_standalone())
