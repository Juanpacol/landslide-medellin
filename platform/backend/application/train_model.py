"""
Caso de uso: reentrenar el modelo y regenerar el reporte.

Wrapper fino sobre ml/train.py (el motor de entrenamiento) + ml/evaluation
(reporte). Existe para que API/scheduler/futuros jobs tengan UN punto de
entrada, y para que la regla "el reporte se regenera junto al modelo" viva
en un solo lugar. `python -m ml.train` (GitHub Actions) sigue funcionando:
su main() delega aquí.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run_training() -> dict[str, Any]:
    """Entrena (si la señal lo permite) y regenera report.md. Devuelve el
    payload de métricas de la corrida (ver ml/train.py::train)."""
    from ml.train import train

    payload = train()

    # El reporte lee metrics.json + best_model.pkl; si la corrida abortó,
    # ambos siguen describiendo al modelo vigente (escritura atómica).
    try:
        from ml.evaluation import generate_report

        generate_report()
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo regenerar report.md (no crítico)")

    return payload
