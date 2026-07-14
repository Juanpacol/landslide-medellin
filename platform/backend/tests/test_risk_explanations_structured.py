"""
Tests unitarios para el structured output de `agent/risk_explanations.py`.

Sin red, sin LLM, sin DB — solo ejercitan las funciones puras:
- `_template_explanation_structured()`: template determinístico → dict.
- `_render_narrative()`: dict estructurado → párrafo humano.
- `_validate_structured()`: validación de la respuesta JSON de OpenRouter.

No requieren `require_ollama` ni `db_session` porque no tocan red ni Postgres.
"""

from __future__ import annotations

import pytest

from agent.risk_explanations import (
    _EXPLANATION_SCHEMA_HINT,
    _render_narrative,
    _template_explanation_structured,
    _validate_structured,
)

_EXPECTED_KEYS = {"title", "factors", "urgency", "recommended_action"}

_CASES = [
    # (risk_category, risk_score, precip_acum_mm, threshold_mm, n_events_7d, is_ladera)
    ("bajo", 0.10, 5.0, 35.0, 0, False),
    ("medio", 0.45, 22.0, 35.0, 0, True),
    ("alto", 0.75, 40.0, 35.0, 2, True),
    ("critico", 0.95, 60.0, 35.0, 3, True),
]


@pytest.mark.parametrize(
    "risk_category,risk_score,precip_acum_mm,threshold_mm,n_events_7d,is_ladera",
    _CASES,
)
def test_template_explanation_structured_has_expected_schema(
    risk_category, risk_score, precip_acum_mm, threshold_mm, n_events_7d, is_ladera
):
    structured = _template_explanation_structured(
        commune_id="13",
        nombre="San Javier",
        risk_score=risk_score,
        risk_category=risk_category,
        precip_acum_mm=precip_acum_mm,
        threshold_mm=threshold_mm,
        n_events_7d=n_events_7d,
        is_ladera=is_ladera,
    )

    assert isinstance(structured, dict)
    assert _EXPECTED_KEYS.issubset(structured.keys())

    assert isinstance(structured["title"], str) and structured["title"].strip()

    assert isinstance(structured["factors"], list) and len(structured["factors"]) >= 1
    assert all(isinstance(f, str) and f.strip() for f in structured["factors"])

    assert structured["urgency"] in {"bajo", "medio", "alto", "critico"}
    # La urgencia estructurada debe reflejar la categoría de riesgo pedida.
    assert structured["urgency"] == risk_category

    assert isinstance(structured["recommended_action"], str) and structured["recommended_action"].strip()


@pytest.mark.parametrize(
    "risk_category,risk_score,precip_acum_mm,threshold_mm,n_events_7d,is_ladera",
    _CASES,
)
def test_render_narrative_produces_nonempty_text_with_title(
    risk_category, risk_score, precip_acum_mm, threshold_mm, n_events_7d, is_ladera
):
    structured = _template_explanation_structured(
        commune_id="13",
        nombre="San Javier",
        risk_score=risk_score,
        risk_category=risk_category,
        precip_acum_mm=precip_acum_mm,
        threshold_mm=threshold_mm,
        n_events_7d=n_events_7d,
        is_ladera=is_ladera,
    )

    narrative = _render_narrative(structured)

    assert isinstance(narrative, str) and narrative.strip()
    assert narrative.endswith(".")
    # El título (sin el punto final que pudiera tener) debe aparecer en el narrativo.
    assert structured["title"].rstrip(".") in narrative
    # Cada factor debe estar presente en el texto narrativo.
    for factor in structured["factors"]:
        assert factor.rstrip(".") in narrative
    assert structured["recommended_action"].rstrip(".") in narrative


def test_render_narrative_empty_dict_returns_empty_string():
    assert _render_narrative({}) == ""


class TestValidateStructured:
    """`_validate_structured` es la puerta de entrada de las respuestas JSON
    del LLM (OpenRouter). Debe aceptar solo estructuras completas y bien
    tipadas, y rechazar (retornar None) cualquier cosa incompleta — mismo
    criterio de "cero alucinaciones toleradas" que rige el resto del archivo.
    """

    def test_accepts_well_formed_payload(self):
        payload = {
            "title": "San Javier en riesgo alto",
            "factors": ["Lluvia acumulada de 40 mm supera el umbral", "2 eventos recientes"],
            "urgency": "alto",
            "recommended_action": "Inspeccionar laderas hoy.",
        }
        result = _validate_structured(payload)
        assert result is not None
        assert result["title"] == payload["title"]
        assert result["factors"] == payload["factors"]
        assert result["urgency"] == "alto"
        assert result["recommended_action"] == payload["recommended_action"]

    def test_normalizes_urgency_case(self):
        payload = {
            "title": "Título",
            "factors": ["factor 1"],
            "urgency": "CRITICO",
            "recommended_action": "Actuar ya.",
        }
        result = _validate_structured(payload)
        assert result is not None
        assert result["urgency"] == "critico"

    @pytest.mark.parametrize(
        "missing_key",
        ["title", "factors", "urgency", "recommended_action"],
    )
    def test_rejects_missing_key(self, missing_key):
        payload = {
            "title": "Título",
            "factors": ["factor 1"],
            "urgency": "medio",
            "recommended_action": "Vigilar.",
        }
        del payload[missing_key]
        assert _validate_structured(payload) is None

    def test_rejects_empty_factors_list(self):
        payload = {
            "title": "Título",
            "factors": [],
            "urgency": "medio",
            "recommended_action": "Vigilar.",
        }
        assert _validate_structured(payload) is None

    def test_rejects_invalid_urgency_value(self):
        payload = {
            "title": "Título",
            "factors": ["factor 1"],
            "urgency": "extremo",  # no está en el enum permitido
            "recommended_action": "Vigilar.",
        }
        assert _validate_structured(payload) is None

    def test_rejects_non_dict_input(self):
        assert _validate_structured(["not", "a", "dict"]) is None
        assert _validate_structured(None) is None
        assert _validate_structured("string") is None


def test_schema_hint_mentions_all_expected_keys():
    """Sanity check: el hint que se envía al LLM menciona las 4 claves del schema."""
    for key in _EXPECTED_KEYS:
        assert key in _EXPLANATION_SCHEMA_HINT
