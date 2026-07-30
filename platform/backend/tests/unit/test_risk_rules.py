"""Tests puros de domain/risk_rules.py. Sin BD, sin red.

Covers: score->category thresholds (boundary values at exactly 0.35/0.65/0.90),
category normalization/display, and the Green/Yellow/Red composite alert state.
"""

from __future__ import annotations

import pytest

from domain.risk_rules import (
    RISK_ALTO,
    RISK_BAJO,
    RISK_CATEGORIES,
    RISK_CRITICO,
    RISK_MEDIO,
    RISK_THRESHOLD_ALTO,
    RISK_THRESHOLD_CRITICO,
    RISK_THRESHOLD_MEDIO,
    alert_level,
    compute_alert_state,
    display_label,
    is_alert_category,
    normalize_category,
    risk_level_from_score,
)


class TestRiskLevelFromScore:
    def test_none_returns_bajo(self):
        assert risk_level_from_score(None) == RISK_BAJO

    def test_zero_is_bajo(self):
        assert risk_level_from_score(0.0) == RISK_BAJO

    def test_negative_score_is_bajo(self):
        # Not a valid score, but the function shouldn't raise for it.
        assert risk_level_from_score(-1.0) == RISK_BAJO

    def test_score_above_one_is_critico(self):
        assert risk_level_from_score(1.5) == RISK_CRITICO

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.0, RISK_BAJO),
            (0.10, RISK_BAJO),
            (RISK_THRESHOLD_MEDIO - 0.001, RISK_BAJO),
            (RISK_THRESHOLD_MEDIO, RISK_MEDIO),
            (RISK_THRESHOLD_MEDIO + 0.001, RISK_MEDIO),
            (0.50, RISK_MEDIO),
            (RISK_THRESHOLD_ALTO - 0.001, RISK_MEDIO),
            (RISK_THRESHOLD_ALTO, RISK_ALTO),
            (RISK_THRESHOLD_ALTO + 0.001, RISK_ALTO),
            (0.80, RISK_ALTO),
            (RISK_THRESHOLD_CRITICO - 0.001, RISK_ALTO),
            (RISK_THRESHOLD_CRITICO, RISK_CRITICO),
            (RISK_THRESHOLD_CRITICO + 0.001, RISK_CRITICO),
            (1.0, RISK_CRITICO),
        ],
    )
    def test_thresholds(self, score, expected):
        assert risk_level_from_score(score) == expected

    def test_accepts_int_like_string_via_float_cast(self):
        # float(score) is called internally; an int should work fine.
        assert risk_level_from_score(1) == RISK_CRITICO

    def test_invalid_type_raises(self):
        with pytest.raises((TypeError, ValueError)):
            risk_level_from_score("not-a-number")


class TestNormalizeCategory:
    def test_none_returns_empty_string(self):
        assert normalize_category(None) == ""

    def test_lowercase_no_accent_passthrough(self):
        assert normalize_category("bajo") == "bajo"

    def test_uppercase_normalized(self):
        assert normalize_category("ALTO") == "alto"

    def test_accented_normalized(self):
        assert normalize_category("Crítico") == "critico"

    def test_padded_whitespace_stripped(self):
        assert normalize_category("  Medio  ") == "medio"

    def test_non_string_input_coerced(self):
        assert normalize_category(123) == "123"


class TestIsAlertCategory:
    @pytest.mark.parametrize("value", ["alto", "ALTO", "Alto", "critico", "Crítico"])
    def test_alert_categories(self, value):
        assert is_alert_category(value) is True

    @pytest.mark.parametrize("value", ["bajo", "medio", "", None, "unknown"])
    def test_non_alert_categories(self, value):
        assert is_alert_category(value) is False


class TestDisplayLabel:
    def test_all_canonical_categories_have_labels(self):
        for cat in RISK_CATEGORIES:
            label = display_label(cat)
            assert label != "Sin datos"

    def test_critico_has_accent(self):
        assert display_label("critico") == "Crítico"

    def test_unknown_category_returns_sin_datos(self):
        assert display_label("no-existe") == "Sin datos"

    def test_none_returns_sin_datos(self):
        assert display_label(None) == "Sin datos"


class TestAlertLevel:
    def test_critico_is_rojo(self):
        assert alert_level("critico") == "Rojo"

    def test_alto_is_naranja(self):
        assert alert_level("alto") == "Naranja"

    def test_bajo_has_no_alert_level(self):
        assert alert_level("bajo") is None

    def test_medio_has_no_alert_level(self):
        assert alert_level("medio") is None

    def test_none_has_no_alert_level(self):
        assert alert_level(None) is None


class TestComputeAlertState:
    def test_critico_category_forces_rojo_regardless_of_rain(self):
        result = compute_alert_state(0.0, 0.0, "critico")
        assert result["state"] == "ROJO"

    def test_high_rain_and_antecedent_forces_rojo(self):
        result = compute_alert_state(1.0, 0.8, "bajo")
        assert result["state"] == "ROJO"

    def test_rain_below_red_threshold_does_not_force_rojo(self):
        result = compute_alert_state(0.99, 0.8, "bajo")
        assert result["state"] != "ROJO"

    def test_alto_category_forces_amarillo(self):
        result = compute_alert_state(0.0, 0.0, "alto")
        assert result["state"] == "AMARILLO"

    def test_rain_at_yellow_threshold_is_amarillo(self):
        result = compute_alert_state(0.6, 0.0, "bajo")
        assert result["state"] == "AMARILLO"

    def test_antecedent_at_yellow_threshold_is_amarillo(self):
        result = compute_alert_state(0.0, 0.6, "medio")
        assert result["state"] == "AMARILLO"

    def test_low_everything_is_verde(self):
        result = compute_alert_state(0.0, 0.0, "bajo")
        assert result["state"] == "VERDE"

    def test_verde_state_has_action_text(self):
        result = compute_alert_state(0.0, 0.0, "bajo")
        assert result["action"] == "Monitoreo rutinario"

    def test_rojo_state_has_action_text(self):
        result = compute_alert_state(0.0, 0.0, "critico")
        assert result["action"] == "Evacuación inmediata hacia zona segura"

    def test_amarillo_state_has_action_text(self):
        result = compute_alert_state(0.0, 0.0, "alto")
        assert result["action"] == "Alistamiento: verificar rutas de evacuación y kit de emergencia"

    def test_accepts_normalized_and_raw_category(self):
        assert compute_alert_state(0.0, 0.0, "Crítico")["state"] == "ROJO"
        assert compute_alert_state(0.0, 0.0, "CRITICO")["state"] == "ROJO"

    def test_returns_dict_with_exactly_state_and_action_keys(self):
        result = compute_alert_state(0.0, 0.0, "bajo")
        assert set(result.keys()) == {"state", "action"}
