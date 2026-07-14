"""Prediction observability: log all ML predictions for monitoring and drift detection."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PREDICTIONS_LOG_FILE = Path(__file__).resolve().parent / "predictions.jsonl"
PREDICTIONS_LOG_FILE.parent.mkdir(exist_ok=True, parents=True)


def log_prediction(
    commune_id: str,
    risk_score: float,
    risk_category: str,
    confidence: float,
    model_version: str,
    features_used: dict[str, Any] | None = None,
    explanation_text: str | None = None,
    explanation_by: str | None = None,
    latency_ms: float | None = None,
) -> None:
    """
    Log a prediction to predictions.jsonl for observability.

    Fields: timestamp, commune_id, risk_score, risk_category, confidence,
            model_version, features_count, latency_ms, explanation_by
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commune_id": commune_id,
        "risk_score": risk_score,
        "risk_category": risk_category,
        "confidence": confidence,
        "model_version": model_version,
        "features_count": len(features_used or {}),
        "latency_ms": latency_ms,
        "explanation_by": explanation_by or "unknown",
    }

    try:
        with open(PREDICTIONS_LOG_FILE, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.error(f"Failed to log prediction: {e}")


def get_prediction_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch last N prediction logs."""
    if not PREDICTIONS_LOG_FILE.exists():
        return []

    logs = []
    try:
        with open(PREDICTIONS_LOG_FILE) as f:
            for line in f.readlines()[-limit:]:
                if line.strip():
                    logs.append(json.loads(line))
    except Exception as e:
        logger.error(f"Failed to read prediction logs: {e}")

    return logs
