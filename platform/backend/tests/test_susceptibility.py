"""
Tests del índice de amenaza = susceptibilidad × disparador.

Este índice SUSTITUYE al clasificador como fuente del `risk_score`, así que
alimenta el dashboard y las alertas Slack a Gestión del Riesgo. Los tests cubren
sobre todo los modos de fallo silencioso: un componente ausente que se lee como
"seguro", un score inventado a partir de datos que no existen, y la compresión
hacia cero que haría el índice inservible contra los umbrales vigentes.
"""

from __future__ import annotations

import pytest

from domain.risk_rules import (
    RISK_THRESHOLD_ALTO,
    RISK_THRESHOLD_CRITICO,
    RISK_THRESHOLD_MEDIO,
    risk_level_from_score,
)
from domain.susceptibility import (
    SEISMIC_MAX_BOOST,
    W_HAZARD,
    W_SLOPE,
    hazard_score,
    normalize_hazard_grade,
    normalize_ndvi,
    normalize_prior_events,
    normalize_slope,
    normalize_twi,
    susceptibility_breakdown,
    susceptibility_index,
    trigger_breakdown,
)

# ── Normalizaciones ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("deg", "esperado"),
    [(0.0, 0.0), (10.0, 0.0), (27.5, 0.5), (45.0, 1.0), (80.0, 1.0)],
)
def test_normalize_slope(deg: float, esperado: float) -> None:
    assert normalize_slope(deg) == pytest.approx(esperado)


def test_normalize_slope_satura_en_ambos_extremos() -> None:
    """Una ladera de 80° no es "más deslizable" que una de 45°: ya no sostiene
    material. Y una de 2° no es negativa."""
    assert normalize_slope(200.0) == 1.0
    assert normalize_slope(-5.0) == 0.0


def test_normalize_ndvi_esta_invertido() -> None:
    """Vegetación densa estabiliza; suelo desnudo no."""
    assert normalize_ndvi(0.8) == pytest.approx(0.0)  # densa → poco susceptible
    assert normalize_ndvi(0.1) == pytest.approx(1.0)  # desnudo → muy susceptible
    assert normalize_ndvi(0.45) == pytest.approx(0.5)
    # Fuera de rango satura, no explota.
    assert normalize_ndvi(0.95) == 0.0
    assert normalize_ndvi(-0.2) == 1.0


def test_normalize_twi() -> None:
    assert normalize_twi(3.0) == pytest.approx(0.0)
    assert normalize_twi(15.0) == pytest.approx(1.0)
    assert normalize_twi(9.0) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Alta", 0.85),
        ("alta", 0.85),
        ("ALTA", 0.85),
        ("Muy alta", 1.0),
        ("Media", 0.5),
        ("Moderada", 0.5),
        ("Baja", 0.15),
        ("Amenaza alta por movimientos en masa", 0.85),
        ("Zona de amenaza muy alta", 1.0),
    ],
)
def test_normalize_hazard_grade(texto: str, esperado: float) -> None:
    assert normalize_hazard_grade(texto) == pytest.approx(esperado)


def test_muy_alta_no_se_confunde_con_alta() -> None:
    """La coincidencia parcial va de más largo a más corto; si no, "muy alta"
    caería en "alta" y se perdería el grado máximo."""
    assert normalize_hazard_grade("muy alta") == 1.0
    assert normalize_hazard_grade("alta") == 0.85
    assert normalize_hazard_grade("muy alta") > normalize_hazard_grade("alta")


def test_grado_desconocido_es_none_no_cero() -> None:
    """0.0 significaría "sin amenaza"; None significa "no tengo el dato". Son
    cosas distintas y confundirlas es un fallo silencioso peligroso."""
    assert normalize_hazard_grade("qwerty") is None
    assert normalize_hazard_grade("") is None
    assert normalize_hazard_grade(None) is None
    assert normalize_hazard_grade("Sin amenaza") == 0.0  # esto SÍ es un cero real


def test_normalize_prior_events_satura() -> None:
    assert normalize_prior_events(0) == 0.0
    assert normalize_prior_events(4) == pytest.approx(0.5)
    assert normalize_prior_events(100) == pytest.approx(1.0, abs=1e-6)
    # Saturante: de 0 a 2 informa más que de 8 a 10.
    salto_bajo = normalize_prior_events(2) - normalize_prior_events(0)
    salto_alto = normalize_prior_events(10) - normalize_prior_events(8)
    assert salto_bajo > salto_alto


def test_normalize_prior_events_negativo_no_rompe() -> None:
    assert normalize_prior_events(-3) == 0.0


# ── Susceptibilidad: renormalización de pesos ─────────────────────────────────


def test_con_todos_los_componentes_los_pesos_suman_uno() -> None:
    b = susceptibility_breakdown(
        slope_p90_deg=27.5,
        twi_p90=9.0,
        ndvi_min=0.45,
        hazard_grade="Media",
        prior_event_count=4,
    )
    assert sum(b.weights_used.values()) == pytest.approx(1.0)
    assert b.coverage == pytest.approx(1.0)
    # Todos los componentes valen 0.5 → el índice es 0.5 sea cual sea el reparto.
    assert b.index == pytest.approx(0.5)


def test_estado_de_hoy_solo_hazard_grade() -> None:
    """El caso REAL al desplegar: solo VM_05 está poblado. El índice debe reflejar
    la amenaza oficial, no diluirse a ~0.21 por los 4 componentes ausentes."""
    b = susceptibility_breakdown(hazard_grade="Alta")
    assert b.index == pytest.approx(0.85)
    assert b.coverage == pytest.approx(W_HAZARD)
    assert b.weights_used == {"hazard": pytest.approx(1.0)}


def test_componente_ausente_no_arrastra_el_indice_a_la_baja() -> None:
    """Sin renormalizar, faltar 4 de 5 componentes daría 0.85×0.25 = 0.21, que se
    leería como "poco susceptible" cuando la verdad es "no sabemos lo demás"."""
    solo_hazard = susceptibility_breakdown(hazard_grade="Alta").index
    assert solo_hazard is not None and solo_hazard > 0.8


def test_coverage_distingue_medicion_de_conjetura() -> None:
    parcial = susceptibility_breakdown(hazard_grade="Alta")
    completo = susceptibility_breakdown(
        slope_p90_deg=40.0,
        twi_p90=12.0,
        ndvi_min=0.2,
        hazard_grade="Alta",
        prior_event_count=3,
    )
    assert parcial.coverage < completo.coverage == pytest.approx(1.0)


def test_sin_ningun_dato_el_indice_es_none() -> None:
    b = susceptibility_breakdown()
    assert b.index is None
    assert b.coverage == 0.0
    assert b.weights_used == {}


def test_el_desglose_expone_los_componentes_para_auditar() -> None:
    b = susceptibility_breakdown(slope_p90_deg=45.0, hazard_grade="Baja")
    assert b.components["slope"] == pytest.approx(1.0)
    assert b.components["hazard"] == pytest.approx(0.15)
    assert b.components["twi"] is None
    # Pesos efectivos proporcionales a los declarados (se reportan redondeados
    # a 4 decimales, de ahí la tolerancia absoluta).
    assert b.weights_used["slope"] == pytest.approx(W_SLOPE / (W_SLOPE + W_HAZARD), abs=1e-4)
    assert sum(b.weights_used.values()) == pytest.approx(1.0, abs=1e-4)


def test_susceptibility_index_es_el_atajo_del_breakdown() -> None:
    kwargs = dict(slope_p90_deg=30.0, hazard_grade="Alta")
    assert susceptibility_index(**kwargs) == susceptibility_breakdown(**kwargs).index


def test_indice_monotono_en_la_pendiente() -> None:
    previo = -1.0
    for deg in (10, 20, 30, 40, 45):
        v = susceptibility_index(slope_p90_deg=float(deg), hazard_grade="Media")
        assert v is not None and v > previo
        previo = v


# ── Disparador ────────────────────────────────────────────────────────────────


def test_lluvia_toma_el_maximo_no_la_media() -> None:
    """SWI e índice antecedente miden lo mismo (agua en el suelo); promediarlos
    diluiría una señal alta con una baja."""
    t = trigger_breakdown(soil_water_index_pct=90.0, antecedent_precip_mm=10.0)
    assert t["rain"] == pytest.approx(0.9)


def test_el_sismo_modula_pero_no_dispara_solo() -> None:
    """Sin lluvia no hay disparador, por intenso que sea el sismo: en Medellín el
    detonante dominante es el agua."""
    assert trigger_breakdown(seismic_intensity=100.0)["trigger"] is None


def test_el_sismo_realza_sobre_suelo_saturado() -> None:
    seco = trigger_breakdown(soil_water_index_pct=60.0)
    con_sismo = trigger_breakdown(soil_water_index_pct=60.0, seismic_intensity=30.0)
    assert con_sismo["trigger"] > seco["trigger"]
    assert con_sismo["trigger"] == pytest.approx(0.6 * (1 + SEISMIC_MAX_BOOST))


def test_el_disparador_no_pasa_de_uno() -> None:
    t = trigger_breakdown(soil_water_index_pct=100.0, seismic_intensity=999.0)
    assert t["trigger"] == pytest.approx(1.0)


def test_disparador_sin_datos_es_none() -> None:
    assert trigger_breakdown()["trigger"] is None


def test_referencia_antecedente_configurable() -> None:
    t = trigger_breakdown(antecedent_precip_mm=50.0, antecedent_reference_mm=100.0)
    assert t["antecedent"] == pytest.approx(0.5)


# ── Amenaza compuesta ─────────────────────────────────────────────────────────


def test_media_geometrica_conserva_la_escala() -> None:
    """El PRODUCTO daría 0.25 y con umbral medio en 0.35 se leería "bajo" un caso
    de susceptibilidad media con suelo medio saturado. La media geométrica da 0.5."""
    assert hazard_score(0.5, 0.5) == pytest.approx(0.5)
    assert hazard_score(0.5, 0.5) > RISK_THRESHOLD_MEDIO


def test_cero_en_cualquier_factor_anula_la_amenaza() -> None:
    """Física: sin disparador no hay deslizamiento; en terreno plano tampoco."""
    assert hazard_score(0.9, 0.0) == 0.0
    assert hazard_score(0.0, 0.9) == 0.0


def test_amenaza_none_si_falta_un_factor() -> None:
    """Un score inventado es peor que la ausencia de score cuando alimenta una
    alerta a Gestión del Riesgo."""
    assert hazard_score(None, 0.8) is None
    assert hazard_score(0.8, None) is None
    assert hazard_score(None, None) is None


def test_la_amenaza_alcanza_las_categorias_altas() -> None:
    """Con el producto simple, "crítico" (≥0.90) exigiría ambos factores >0.95 y
    sería prácticamente inalcanzable. Se comprueba que el índice es utilizable."""
    assert hazard_score(0.95, 0.95) >= RISK_THRESHOLD_CRITICO
    assert hazard_score(0.7, 0.7) >= RISK_THRESHOLD_ALTO
    assert risk_level_from_score(hazard_score(0.95, 0.95)) == "critico"
    assert risk_level_from_score(hazard_score(0.7, 0.7)) == "alto"


def test_amenaza_monotona_y_simetrica() -> None:
    assert hazard_score(0.4, 0.9) == hazard_score(0.9, 0.4)
    previo = -1.0
    for t in (0.2, 0.4, 0.6, 0.8, 1.0):
        v = hazard_score(0.6, t)
        assert v is not None and v > previo
        previo = v


def test_amenaza_en_rango_cero_uno() -> None:
    for s in (0.0, 0.25, 0.5, 0.75, 1.0):
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            v = hazard_score(s, t)
            assert v is not None and 0.0 <= v <= 1.0


def test_caso_realista_villa_hermosa() -> None:
    """Comuna 8, ladera con amenaza alta, tras varios días de lluvia."""
    s = susceptibility_index(hazard_grade="Alta", slope_p90_deg=32.0)
    t = trigger_breakdown(soil_water_index_pct=78.0, seismic_intensity=5.0)["trigger"]
    score = hazard_score(s, t)
    assert score is not None
    assert risk_level_from_score(score) in {"alto", "critico"}


# ── Frontera con risk_rules ───────────────────────────────────────────────────


def test_no_se_duplican_umbrales_de_alerta() -> None:
    """`domain/susceptibility.py` produce el score; `domain/risk_rules.py` decide
    la categoría. Si los umbrales se copian aquí, las dos capas divergirán.

    Se inspecciona solo el CÓDIGO, no el docstring: el docstring cita los
    umbrales a propósito, para explicar que aplicarlos a este índice es una
    decisión de continuidad operativa y no una equivalencia demostrada.
    """
    import domain.susceptibility as mod

    # Se comprueba la API PÚBLICA, no el texto fuente. Escanear el código da
    # falsos positivos: `SEISMIC_MAX_BOOST` vale 0.35 por coincidencia con el
    # umbral medio, y los comentarios mencionan "alto" para explicar la
    # saturación sísmica. Ninguna de las dos cosas es una duplicación.
    publicos = {n for n in dir(mod) if not n.startswith("_")}
    for prohibido in (
        "risk_level_from_score",
        "normalize_category",
        "display_label",
        "alert_level",
        "compute_alert_state",
        "is_alert_category",
    ):
        assert prohibido not in publicos, (
            f"susceptibility.py reimplementa {prohibido}, que pertenece a risk_rules"
        )
    assert not any(n.startswith("RISK_THRESHOLD") for n in publicos)
    assert not any("ALERT" in n.upper() for n in publicos)

    # El contrato de salida son escalares y None, nunca categorías.
    assert isinstance(hazard_score(0.6, 0.6), float)
    assert isinstance(susceptibility_index(hazard_grade="Alta"), float)


def test_la_calibracion_esta_declarada() -> None:
    """No esconder en un comentario que nada de esto está calibrado: la API y el
    dashboard tienen que poder decirlo."""
    from domain.susceptibility import CALIBRATION_NOTE, CALIBRATION_STATUS

    assert CALIBRATION_STATUS == "no_calibrado"
    assert "recalibrar" in CALIBRATION_NOTE.lower()
