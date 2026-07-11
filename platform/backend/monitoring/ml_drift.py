"""Agente: detecta degradación del modelo ML (drift) contra el benchmark fijo.

Corre tras cada corrida de `ml.predict` (post-predicción batch).
Reusa `ml.benchmark.evaluate_benchmark` — el mismo scoring que usa
`ml.train.py` contra `ml/models/benchmark.json` — para no reimplementar
AUC con una fuente de verdad distinta ni arriesgar fuga de datos del futuro.

Compara:
- benchmark_auc actual (recomputado contra el modelo en producción) vs.
  el benchmark_auc que quedó grabado en metrics.json la última vez que se
  entrenó (umbral: cae >2 puntos porcentuales = crítico).
- Distribución de risk_category en predicciones recientes vs. lo esperado
  (umbral: >30% de predicciones en categoría crítica = warning, posible
  sobre-alerta del modelo o cambio real de condiciones).

Resultado → agent_run_logs + alerta Slack si warning/critical.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from db.models.risk_prediction import RiskPrediction
from db.session import AsyncSessionLocal, SyncSessionLocal
from monitoring.notify import fire_agent_alert

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "ml" / "models"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"
METRICS_PATH = MODELS_DIR / "metrics.json"

AUC_DEGRADATION_THRESHOLD = 0.02  # >2 puntos porcentuales
CRITICAL_SHARE_WARNING_THRESHOLD = 0.30  # >30% de predicciones recientes en "critico"


def _load_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def recompute_benchmark_auc() -> dict:
    """Recalcula benchmark_auc contra el modelo actualmente en producción.

    Reusa ml.benchmark.evaluate_benchmark (misma lógica que ml.train.py),
    con sesión sync porque esa función usa sqlalchemy.orm.Session, no async.
    """
    import joblib

    from ml.benchmark import evaluate_benchmark
    from ml.features import FeatureBuilder

    if not BEST_MODEL_PATH.exists():
        return {"benchmark_auc": None, "reason": "best_model.pkl no existe"}

    artifact = joblib.load(BEST_MODEL_PATH)
    if not isinstance(artifact, dict) or "model" not in artifact:
        return {"benchmark_auc": None, "reason": "artefacto de modelo inválido"}

    model = artifact["model"]
    feature_names = list(artifact.get("feature_names") or [])

    builder = FeatureBuilder(MODELS_DIR)
    scaler_path = builder.scaler_path()
    if not scaler_path.exists():
        return {"benchmark_auc": None, "reason": "scaler.pkl no existe"}
    scaler = joblib.load(scaler_path)

    with SyncSessionLocal() as session:
        return evaluate_benchmark(model, scaler, feature_names, session) or {
            "benchmark_auc": None,
            "reason": "evaluate_benchmark devolvió vacío",
        }


async def check_risk_category_distribution() -> dict:
    """Distribución de risk_category en predicciones de los últimos 7 días."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(RiskPrediction.risk_category, func.count())
            .where(RiskPrediction.created_at >= cutoff)
            .group_by(RiskPrediction.risk_category)
        )
        rows = (await session.execute(stmt)).all()

    counts = {category: n for category, n in rows}
    total = sum(counts.values())
    critical_share = (counts.get("critico", 0) / total) if total else 0.0

    return {
        "total_predictions_7d": total,
        "by_category": counts,
        "critical_share": round(critical_share, 3),
    }


async def run() -> None:
    """Ejecuta drift detection y reporta a Slack."""
    baseline = _load_metrics()
    baseline_auc = baseline.get("benchmark_auc")

    findings: dict = {}
    worst_status = "ok"

    try:
        current = recompute_benchmark_auc()
        current_auc = current.get("benchmark_auc")

        if current_auc is None:
            findings["benchmark_check"] = {"status": "SKIPPED", **current}
        elif baseline_auc is None:
            findings["benchmark_check"] = {
                "status": "SKIPPED",
                "reason": "metrics.json no tiene benchmark_auc grabado (correr ml.train)",
                "current_auc": round(current_auc, 4),
            }
        else:
            drop = baseline_auc - current_auc
            findings["benchmark_check"] = {
                "baseline_auc": round(baseline_auc, 4),
                "current_auc": round(current_auc, 4),
                "drop": round(drop, 4),
                "threshold": AUC_DEGRADATION_THRESHOLD,
            }
            if drop > AUC_DEGRADATION_THRESHOLD:
                worst_status = "critical"
                findings["benchmark_check"]["status"] = "CRITICAL"
            else:
                findings["benchmark_check"]["status"] = "OK"

        dist = await check_risk_category_distribution()
        findings["category_distribution"] = dist
        if dist["total_predictions_7d"] > 0 and dist["critical_share"] > CRITICAL_SHARE_WARNING_THRESHOLD:
            if worst_status != "critical":
                worst_status = "warning"
            findings["category_distribution"]["status"] = "WARNING"
        else:
            findings["category_distribution"]["status"] = "OK"

        async with AsyncSessionLocal() as session:
            await fire_agent_alert(
                session,
                agent_name="ml-drift-detector",
                status=worst_status,
                summary=f"ML drift detection: {worst_status.upper()}",
                detail=findings if worst_status != "ok" else None,
            )

    except Exception as e:
        logger.exception("ML drift detection failed")
        try:
            async with AsyncSessionLocal() as session:
                await fire_agent_alert(
                    session,
                    agent_name="ml-drift-detector",
                    status="error",
                    summary=f"ML drift detection error: {e}",
                )
        except Exception:
            logger.exception("Failed to report ML drift error")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
