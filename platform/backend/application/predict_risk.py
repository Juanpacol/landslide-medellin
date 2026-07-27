"""
Caso de uso: correr la predicción de riesgo para todo el territorio.

Orquesta (movido desde ml/predict.py::predict_all_comunas):
  1. inferencia por comuna (ml/predict.py::predict_risk — el motor ML),
  2. explicación en lenguaje natural (agent/risk_explanations),
  3. persistencia (RiskPrediction + RiskExplanation) y observabilidad,
  4. checks de alertas post-predicción (application/fire_alerts).

ml/predict.py mantiene `predict_all_comunas()` como wrapper fino porque el
workflow de GitHub Actions invoca `python -m ml.predict` y la API lo importa.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fire_alerts import alerts_after_prediction
from db.models.risk_explanation import RiskExplanation
from db.models.risk_prediction import RiskPrediction
from domain.communes import COMMUNES
from errors.error_handler import BusinessError, TeyvaError, TransientError, handle_errors

# predict_risk() por comuna no tenía NINGÚN try/except: una excepción sin
# capturar (datos faltantes, fallo de I/O al construir features) abortaba
# el loop completo y ninguna de las 21 comunas se comiteaba, porque el
# commit ocurre una sola vez al final. Este fallback es lo que devuelve
# _predict_one_commune cuando una comuna puntual falla, para que las demás
# sigan procesándose.
_PREDICTION_FALLBACK: dict[str, Any] = {
    "risk_score": 0.0,
    "risk_level": "bajo",
    "confidence": 0.0,
    "features_used": {},
    "error": "fallo al predecir esta comuna (ver logs)",
}


def _classify_predict_exception(exc: Exception) -> TeyvaError:
    """I/O externo (BD, filesystem, red) es transitorio y candidato a
    retry; cualquier otra falla (features faltantes/corruptas) es un
    estado de negocio esperado para una comuna puntual — no debe abortar
    las demás."""
    if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
        return TransientError(str(exc))
    return BusinessError(str(exc))


async def _predict_one_uncategorized(cid: str, db: AsyncSession) -> dict[str, Any]:
    from ml.predict import predict_risk

    try:
        return await predict_risk(cid, db)
    except Exception as exc:  # noqa: BLE001
        raise _classify_predict_exception(exc) from exc


_predict_one_commune = handle_errors(
    "predict_risk_commune", fallback=_PREDICTION_FALLBACK, retries=2
)(_predict_one_uncategorized)


async def run_predictions(db: AsyncSession) -> None:
    """Predice, explica y persiste para las 21 comunas; luego dispara alertas."""
    from agent.risk_explanations import generate_risk_explanation
    from ml.predict import _load_metrics
    from observability.predictions import log_prediction

    metrics = _load_metrics()
    model_version = str(metrics.get("model_version") or "teyva-ml-1.0")

    for commune in COMMUNES:
        cid = commune.id
        out = await _predict_one_commune(cid, db)
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

        # Explicación en lenguaje natural (LLM si hay API key, template si no).
        try:
            precip_mm = float(
                features_used.get("precip_sum_mm_day")
                or features_used.get("mean_precip_mm_snapshot")
                or 0.0
            )
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
        except Exception:  # noqa: BLE001
            explanation_text = (
                f"Probabilidad estimada de evento en 7 días: {risk_score:.3f} (nivel {risk_level})."
            )
            generated_by = "template"
            explanation_structured = None

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
    await alerts_after_prediction(db)
