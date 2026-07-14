"""
Pruebas unitarias de las reglas de negocio de riesgo (domain/risk_rules.py).
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform" / "backend"))

from domain.risk_rules import risk_level_from_score, display_label  # type: ignore


class TestRiskLevelFromScore:
    def test_bajo(self):
        assert risk_level_from_score(0.10) == "bajo"
        assert risk_level_from_score(0.34) == "bajo"

    def test_medio(self):
        assert risk_level_from_score(0.35) == "medio"
        assert risk_level_from_score(0.64) == "medio"

    def test_alto(self):
        assert risk_level_from_score(0.65) == "alto"
        assert risk_level_from_score(0.89) == "alto"

    def test_critico(self):
        assert risk_level_from_score(0.90) == "critico"
        assert risk_level_from_score(1.00) == "critico"

    def test_boundary_medio(self):
        assert risk_level_from_score(0.35) == "medio"

    def test_boundary_alto(self):
        assert risk_level_from_score(0.65) == "alto"

    def test_boundary_critico(self):
        assert risk_level_from_score(0.90) == "critico"


class TestDisplayLabel:
    def test_bajo(self):
        assert display_label("bajo") == "Bajo"

    def test_critico_sin_tilde(self):
        label = display_label("critico")
        assert "tico" in label.lower()

    def test_alto(self):
        assert display_label("alto") == "Alto"

    def test_medio(self):
        assert display_label("medio") == "Medio"
