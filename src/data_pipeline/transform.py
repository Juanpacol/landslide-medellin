"""
transform.py — Procesamiento y vectorización de datos.

Aplica el pipeline de transformación sobre datos crudos para producir
los features listos para entrenamiento e inferencia del modelo ML.

Uso:
    from src.data_pipeline.transform import FeatureTransformer
    transformer = FeatureTransformer()
    df_features = transformer.build_features(commune_id="13", days=30)
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

_BACKEND = Path(__file__).resolve().parents[2] / "platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class FeatureTransformer:
    """
    Construye el vector de features para una comuna a partir de los datos
    almacenados en la base de datos.
    """

    def build_features(self, commune_id: str, days: int = 30) -> dict:
        """
        Construye el diccionario de features para una comuna.

        Args:
            commune_id: ID de la comuna ("1"–"21").
            days:       Ventana de días hacia atrás para calcular acumulados.

        Returns:
            Diccionario con todas las variables del consolidado.
            Ver docs/data_dictionary.md para la definición de cada campo.
        """
        import asyncio
        return asyncio.run(self._async_build(commune_id, days))

    async def _async_build(self, commune_id: str, days: int) -> dict:
        from ml.features import build_feature_vector  # type: ignore
        from db.session import AsyncSessionLocal  # type: ignore
        async with AsyncSessionLocal() as db:
            return await build_feature_vector(commune_id=commune_id, db=db, days=days)

    def vectorize_for_rag(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        Genera embeddings para una lista de textos usando el modelo RAG.

        Args:
            texts:      Lista de textos a vectorizar.
            batch_size: Tamaño del batch (default 32).

        Returns:
            Lista de vectores de embedding (float32).
        """
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        return embeddings.tolist()
