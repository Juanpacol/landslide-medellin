"""
Use case: retrain the model and regenerate the report.

Thin wrapper over ml/train.py (the training engine) + ml/evaluation
(report). Exists so API/scheduler/future jobs have ONE entry point, and so
the rule "the report is regenerated alongside the model" lives in a single
place. `python -m ml.train` (GitHub Actions) keeps working: its main()
delegates here.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_training() -> dict[str, Any]:
    """Trains (if the signal allows it) and regenerates report.md. Returns
    the run's metrics payload (see ml/train.py::train)."""
    from ml.train import train

    payload = train()

    # The report reads metrics.json + best_model.pkl; if the run aborted,
    # both still describe the current model (atomic write).
    try:
        from ml.evaluation import generate_report

        generate_report()
    except Exception:  # noqa: BLE001
        logger.exception("Could not regenerate report.md (non-critical)")

    return payload
