"""Tests puros de domain/validation.py y domain/pii.py. Sin BD."""

from __future__ import annotations

import pytest

from domain.pii import redact_pii
from domain.validation import (
    validate_citizen_report,
    validate_scrape_log_status,
    validate_sensor_reading,
)
from errors.error_handler import ValidationError


class TestValidateScrapeLogStatus:
    def test_acepta_estados_conocidos(self) -> None:
        for status in ("ok", "completed", "success", "failed", "error", "started"):
            assert validate_scrape_log_status(status) == status

    def test_rechaza_estado_desconocido(self) -> None:
        with pytest.raises(ValidationError):
            validate_scrape_log_status("bogus")


class TestValidateCitizenReport:
    def test_rechaza_descripcion_corta(self) -> None:
        with pytest.raises(ValidationError):
            validate_citizen_report("grieta", "1")

    def test_acepta_y_redacta_pii(self) -> None:
        result = validate_citizen_report("Hay una grieta grande, mi celular es 3001234567", "1")
        assert "3001234567" not in result
        assert "grieta grande" in result

    def test_trim_espacios(self) -> None:
        result = validate_citizen_report("   grieta muy visible en la pared   ", "1")
        assert result == "grieta muy visible en la pared"


class TestValidateSensorReading:
    def test_descarta_sentinela(self) -> None:
        assert validate_sensor_reading(-999.0, field="precip_mm") is None

    def test_descarta_fuera_de_rango(self) -> None:
        assert validate_sensor_reading(9999.0, field="precip_mm") is None

    def test_acepta_valor_valido(self) -> None:
        assert validate_sensor_reading(12.5, field="precip_mm") == 12.5

    def test_none_pasa_none(self) -> None:
        assert validate_sensor_reading(None, field="precip_mm") is None


class TestRedactPii:
    def test_redacta_email(self) -> None:
        assert "juan@example.com" not in redact_pii("contacto: juan@example.com")

    def test_redacta_telefono(self) -> None:
        assert "3001234567" not in redact_pii("llámame al 3001234567 porfa")

    def test_texto_sin_pii_no_cambia_significativamente(self) -> None:
        text = "hay una grieta grande en la ladera"
        assert redact_pii(text) == text
