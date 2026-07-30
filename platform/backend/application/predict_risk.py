"""
Use case: run the risk prediction for the entire territory.

Orchestrates (moved from ml/predict.py::predict_all_comunas):
  1. per-commune inference (ml/predict.py::predict_risk — the ML engine),
  2. natural-language explanation (agent/risk_explanations),
  3. persistence (RiskPrediction + RiskExplanation) and observability,
  4. post-prediction alert checks (application/fire_alerts).

ml/predict.py keeps `predict_all_comunas()` as a thin wrapper because the
GitHub Actions workflow invokes `python -m ml.predict` and the API imports it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fire_alerts import alerts_after_prediction
from db.models.risk_explanation import RiskExplanation
from db.models.risk_prediction import RiskPrediction
from domain.communes import COMMUNES
from errors.error_handler import BusinessError, TeyvaError, TransientError, handle_errors

# predict_risk() per commune used to have NO try/except at all: an
# uncaught exception (missing data, I/O failure building features) aborted
# the whole loop and none of the 21 communes got committed, because the
# commit happens only once at the end. This fallback is what
# _predict_one_commune returns when a single commune fails, so the rest
# keep processing.
_PREDICTION_FALLBACK: dict[str, Any] = {
    "risk_score": 0.0,
    "risk_level": "bajo",
    "confidence": 0.0,
    "features_used": {},
    "error": "fallo al predecir esta comuna (ver logs)",
}


def _classify_predict_exception(exc: Exception) -> TeyvaError:
    """External I/O (DB, filesystem, network) is transient and a retry
    candidate; any other failure (missing/corrupt features) is an expected
    business state for a single commune — it must not abort the rest."""
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
    """Predicts, explains and persists for all 21 communes; then fires post-prediction alerts.

    Risk score/level now come from the neuro-symbolic inference engine
    (`application/neurosymbolic/infer.py`): the declared susceptibility × trigger index
    (`ml/hazard.py`) combined with `domain/rules`, replacing the classifier that
    `docs/research/audit-2026-07.md` showed has no valid training target (0 usable positives).
    If the batch inference itself fails (e.g. a hazard-source query errors), each commune falls
    back independently to the legacy classifier path via `_predict_one_commune`, so one failure
    mode never blocks the other.
    """
    from agent.risk_explanations import generate_risk_explanation
    from application.neurosymbolic.infer import infer_all
    from ml.predict import _load_metrics
    from observability.predictions import log_prediction

    metrics = _load_metrics()
    model_version = str(metrics.get("model_version") or "teyva-ml-1.0")

    try:
        verdicts = await infer_all(db)
    except Exception:  # noqa: BLE001
        verdicts = {}

    for commune in COMMUNES:
        cid = commune.id
        verdict = verdicts.get(str(cid))

        if verdict is not None:
            risk_score = float(verdict.score or 0.0)
            risk_level = verdict.level
            confidence = verdict.confidence
            features_used: dict = {}
            raw_output = {
                "features_used": features_used,
                "confidence": confidence,
                "risk_level": risk_level,
                "error": None,
                "derivation": verdict.derivation,
                "conflicts": list(verdict.conflicts),
                "priority": verdict.priority,
                "source": "neurosymbolic",
            }
        else:
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
                "source": "classifier_fallback",
            }

        # Explanation: derivation-grounded (no LLM call, faithful by construction)
        # when a neuro-symbolic Verdict exists; legacy LLM/template path otherwise.
        try:
            if verdict is not None:
                from agent.risk_explanations import generate_explanation_from_verdict

                explanation_text, generated_by, explanation_structured = (
                    generate_explanation_from_verdict(verdict)
                )
            else:
                precip_mm = float(
                    features_used.get("precip_sum_mm_day")
                    or features_used.get("mean_precip_mm_snapshot")
                    or 0.0
                )
                n_events = int(features_used.get("n_events_window") or 0)
                (
                    explanation_text,
                    generated_by,
                    explanation_structured,
                ) = await generate_risk_explanation(
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
