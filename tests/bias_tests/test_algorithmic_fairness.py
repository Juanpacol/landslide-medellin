"""
Pruebas automatizadas de equidad y sesgo algorítmico — TEYVA.

Verifica que el modelo no discrimine sistemáticamente por características
territoriales o demográficas no relacionadas con el riesgo real.
"""
import sys
import json
import numpy as np
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MODELS_PATH = Path("platform/backend/ml/models")


@pytest.fixture(scope="module")
def metrics():
    """Carga las métricas del modelo entrenado."""
    path = MODELS_PATH / "metrics.json"
    if not path.exists():
        pytest.skip("metrics.json no encontrado — ejecutar python -m ml.train primero")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def feature_names():
    path = MODELS_PATH / "feature_names.json"
    if not path.exists():
        pytest.skip("feature_names.json no encontrado")
    with open(path) as f:
        return json.load(f)


class TestModelFairness:
    def test_recall_above_threshold(self, metrics):
        """
        El recall debe ser ≥ 0.95.

        Un recall bajo significaría que el modelo omite eventos reales,
        lo que en contexto de gestión del riesgo puede costar vidas.
        """
        recall = metrics.get("recall", 0)
        assert recall >= 0.95, (
            f"Recall {recall:.3f} es menor al umbral mínimo de 0.95. "
            "El modelo está omitiendo eventos reales de deslizamiento."
        )

    def test_auc_above_threshold(self, metrics):
        """El AUC-ROC debe ser ≥ 0.90 para garantizar discriminación suficiente."""
        auc = metrics.get("auc_roc", 0)
        assert auc >= 0.90, f"AUC-ROC {auc:.3f} está por debajo del umbral mínimo de 0.90."

    def test_no_geographic_proxy_bias(self, feature_names):
        """
        El modelo no debe usar commune_id como feature directa.

        Usar el ID de la comuna como feature puede introducir sesgo
        geográfico: comunas históricamente pobres con menos registros
        DAGRD recibirían menor predicción de riesgo por subregistro,
        no por riesgo real menor.
        """
        prohibited = {"commune_id", "id", "barrio_id", "estrato"}
        used = set(feature_names)
        overlap = prohibited & used
        assert not overlap, (
            f"Variables prohibidas encontradas en el modelo: {overlap}. "
            "Estas pueden introducir sesgo geográfico o socioeconómico."
        )

    def test_synthetic_events_not_in_features(self, feature_names):
        """
        No debe haber features derivadas de eventos sintéticos.

        Los 144 eventos generados por Snake Line están marcados como
        is_synthetic=True y deben estar EXCLUIDOS del entrenamiento.
        """
        synthetic_proxies = {"is_synthetic", "snake_line_score", "synthetic_event"}
        used = set(feature_names)
        overlap = synthetic_proxies & used
        assert not overlap, (
            f"Features potencialmente derivadas de eventos sintéticos: {overlap}. "
            "Esto constituye contaminación circular del modelo."
        )


class TestDataSourceCoverage:
    def test_all_communes_have_features(self, feature_names):
        """
        Verificar que se espera cobertura de las 21 comunas.
        (Prueba conceptual — la cobertura real se verifica en integration tests)
        """
        assert len(feature_names) >= 10, (
            "El modelo usa menos de 10 features. Es posible que falten "
            "fuentes de datos o que el pipeline de features esté incompleto."
        )

    def test_temporal_feature_present(self, feature_names):
        """Debe haber al menos una feature de ventana temporal de precipitación."""
        temporal = [f for f in feature_names if "7d" in f or "3d" in f or "30d" in f]
        assert len(temporal) >= 2, (
            "El modelo no tiene suficientes features temporales. "
            "La precipitación acumulada es el predictor más importante."
        )
