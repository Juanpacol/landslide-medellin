"""
train.py — Scripts de reentrenamiento automático del modelo.

Punto de entrada para lanzar el pipeline de entrenamiento desde fuera
del contexto de la API. Delega en platform/backend/ml/train.py.

Uso desde Python:
    from src.train import ModelTrainer
    trainer = ModelTrainer()
    metrics = trainer.train()

Uso desde terminal (equivalente):
    cd platform/backend && python -m ml.train
"""

from __future__ import annotations
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class ModelTrainer:
    """
    Orquestador del pipeline de entrenamiento del modelo TEYVA.

    Ejecuta las fases:
    1. Carga de datos (ml_features + landslide_events)
    2. Construcción de matriz supervisada
    3. Normalización (StandardScaler)
    4. Balanceo de clases (SMOTE)
    5. Evaluación de candidatos (XGBoost, RandomForest, LogisticRegression)
    6. Selección del mejor modelo por AUC-ROC
    7. Escritura atómica de artefactos (best_model.pkl, scaler.pkl,
       feature_names.json, metrics.json)
    """

    def train(self) -> dict:
        """
        Ejecuta el pipeline completo de entrenamiento.

        Returns:
            Métricas del modelo entrenado:
            {
                "auc_roc": 0.944,
                "recall": 0.999,
                "precision": 0.87,
                "f1": 0.93,
                "trained_at": "...",
                "git_commit_sha": "..."
            }

        Raises:
            RuntimeError: Si el entrenamiento falla antes de escribir artefactos.
                         En ese caso se escribe last_train_attempt.json pero NO
                         se tocan los artefactos de producción.
        """
        import asyncio
        from ml.train import train_model  # type: ignore
        from db.session import AsyncSessionLocal  # type: ignore

        async def _run():
            async with AsyncSessionLocal() as db:
                return await train_model(db=db)

        metrics = asyncio.run(_run())
        print(f"Entrenamiento completado. AUC-ROC: {metrics.get('auc_roc', 'N/A')}")
        return metrics

    def freeze_benchmark(self) -> None:
        """
        Congela las métricas actuales como benchmark de referencia.

        Equivalente a: python -m ml.benchmark --freeze
        """
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "ml.benchmark", "--freeze"],
            cwd=str(_BACKEND),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("Benchmark congelado correctamente.")
        else:
            print(f"Error al congelar benchmark: {result.stderr}")
