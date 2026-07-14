"""
Pruebas unitarias del pipeline de inferencia (src/inference.py).

Nota: estas pruebas usan mocks de la BD y del modelo para poder
ejecutarse sin dependencias externas.
"""
import sys
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.inference import RiskPredictor


class TestRiskPredictor:
    def setup_method(self):
        self.predictor = RiskPredictor()

    def test_get_model_info_missing_file(self, tmp_path, monkeypatch):
        """Retorna mensaje de error si metrics.json no existe."""
        import src.inference as inf_module
        monkeypatch.setattr(inf_module, "_BACKEND", tmp_path)
        (tmp_path / "ml" / "models").mkdir(parents=True)
        result = self.predictor.get_model_info()
        assert "error" in result

    def test_get_model_info_reads_file(self, tmp_path, monkeypatch):
        """Lee y retorna el contenido de metrics.json correctamente."""
        import src.inference as inf_module
        models_dir = tmp_path / "ml" / "models"
        models_dir.mkdir(parents=True)
        metrics = {"auc_roc": 0.944, "recall": 0.999, "trained_at": "2026-07-13"}
        (models_dir / "metrics.json").write_text(json.dumps(metrics))
        monkeypatch.setattr(inf_module, "_BACKEND", tmp_path)
        result = self.predictor.get_model_info()
        assert result["auc_roc"] == 0.944
        assert result["recall"] == 0.999
