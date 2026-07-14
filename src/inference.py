"""
inference.py — Pipeline de ejecución de modelos en producción.

Punto de entrada para predicción de riesgo desde fuera del contexto
de la API. Delega en platform/backend/ml/predict.py.

Uso:
    from src.inference import RiskPredictor
    predictor = RiskPredictor()
    result = predictor.predict_commune("13")
    results = predictor.predict_all()
"""

from __future__ import annotations
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class RiskPredictor:
    """
    Predictor de riesgo de deslizamiento para las 21 comunas de Medellín.

    Carga el modelo entrenado y aplica inferencia sobre los datos actuales
    de la base de datos.
    """

    def predict_commune(self, commune_id: str) -> dict:
        """
        Predice el riesgo para una sola comuna.

        Args:
            commune_id: ID de la comuna ("1"–"21").

        Returns:
            {
                "commune_id": "13",
                "risk_score": 0.72,
                "risk_category": "alto",
                "risk_label": "Alto"
            }
        """
        import asyncio
        from ml.predict import predict_risk  # type: ignore
        from db.session import AsyncSessionLocal  # type: ignore

        async def _run():
            async with AsyncSessionLocal() as db:
                return await predict_risk(commune_id=commune_id, db=db)

        return asyncio.run(_run())

    def predict_all(self) -> None:
        """
        Ejecuta predicciones batch para las 21 comunas.
        Inserta resultados en la tabla risk_predictions.
        """
        import asyncio
        from ml.predict import predict_all_comunas  # type: ignore
        from db.session import AsyncSessionLocal  # type: ignore

        async def _run():
            async with AsyncSessionLocal() as db:
                await predict_all_comunas(db=db)

        asyncio.run(_run())
        print("Predicciones batch completadas para las 21 comunas.")

    def get_model_info(self) -> dict:
        """
        Retorna información sobre el modelo actualmente cargado.

        Returns:
            {
                "auc_roc": 0.944,
                "recall": 0.999,
                "trained_at": "2026-07-13T10:00:00",
                "git_commit_sha": "abc123..."
            }
        """
        import json
        metrics_path = _BACKEND / "ml" / "models" / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                return json.load(f)
        return {"error": "metrics.json not found — run python -m ml.train first"}
