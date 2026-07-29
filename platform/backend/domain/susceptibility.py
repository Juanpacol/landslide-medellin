"""
Amenaza por deslizamiento = **susceptibilidad × disparador**. Puro, sin I/O.

## Por qué esto sustituye al clasificador

TEYVA no tiene etiquetas supervisadas usables (verificado el 2026-07-29): de
5.880 eventos reales en `landslide_events`, 5.844 no tienen ninguna ubicación y
los 36 con comuna son en su mayoría titulares de prensa municipal, no
deslizamientos. Los 26 positivos con los que se entrenó el modelo en producción
venían de los 144 eventos **sintéticos** generados por la Snake Line; al filtrarse
correctamente por `is_synthetic`, las etiquetas desaparecieron.

Un clasificador sin objetivo no es un clasificador. Lo defendible con los datos
que sí existen es la formulación estándar de amenaza:

    amenaza = susceptibilidad (terreno, estático) × disparador (lluvia/sismo, dinámico)

Los pesos son **declarados y documentados**, no aprendidos. Con 26 positivos
—y ahora con 0— aprender 5 pesos es ajustar ruido. Un índice declarado es
auditable, explicable a Gestión del Riesgo y recalibrable el día que exista un
inventario real.

## Frontera con `domain/risk_rules.py`

`risk_rules` es la capa de UMBRALES: convierte un score en categoría y en estado
operativo. Este módulo produce el score. No se invade: aquí no hay ningún umbral
de alerta, y allí no se calcula ninguna amenaza.

## Honestidad sobre la calibración

**Ningún número de este módulo está calibrado contra deslizamientos observados.**
Vienen de literatura y juicio experto, igual que `DRAIN_RATE_DEFAULT` en
`ml/soil_water_index.py`. Los umbrales de `risk_rules` (0.35 / 0.65 / 0.90) se
fijaron para una probabilidad de clasificador, así que aplicarlos a este índice es
una decisión de continuidad operativa, no una equivalencia demostrada. Está
declarado en `CALIBRATION_STATUS` para que aparezca en la API y en el dashboard,
no escondido en un comentario.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

CALIBRATION_STATUS = "no_calibrado"
CALIBRATION_NOTE = (
    "Pesos y rangos de normalización derivados de literatura y juicio experto, "
    "no ajustados contra deslizamientos observados en Medellín. Recalibrar cuando "
    "exista un inventario de eventos con fecha y ubicación (≥100 eventos reales)."
)

# ── Pesos de la susceptibilidad (suman 1.0) ───────────────────────────────────
#
# Si falta un componente, los pesos se RENORMALIZAN sobre los disponibles. Es
# esencial y no un detalle: hoy solo `hazard_grade` está poblado (VM_05 de
# GeoMedellín, 401 barrios), y pendiente/TWI/NDVI llegan cuando se ingesten
# SRTM y MODIS. Sin renormalizar, un índice con 4 de 5 componentes ausentes daría
# ~0.25 y se leería como "poco susceptible" cuando en realidad es "no sabemos".
W_SLOPE = 0.30  # control primario de la estabilidad de una ladera
W_HAZARD = 0.25  # amenaza oficial VM_05: ya validada por geólogos, no descartarla
W_TWI = 0.20  # dónde se acumula el agua
W_PRIOR = 0.15  # "las zonas peligrosas se repiten"
W_NDVI = 0.10  # menos vegetación → menos raíces → menos cohesión

# ── Rangos de normalización ───────────────────────────────────────────────────
# Pendiente: por debajo de 10° los deslizamientos son raros; por encima de 45°
# el material suelto ya no se sostiene, así que se satura.
SLOPE_MIN_DEG = 10.0
SLOPE_MAX_DEG = 45.0
# TWI: adimensional. Valores bajos = divisorias secas; altos = vaguadas donde
# converge el flujo.
TWI_MIN = 3.0
TWI_MAX = 15.0
# NDVI mínimo: ~0.8 es vegetación densa, ~0.1 suelo desnudo. Se INVIERTE.
NDVI_DENSE = 0.8
NDVI_BARE = 0.1
# Densidad de eventos previos: satura rápido — la diferencia entre 0 y 2 eventos
# informa mucho más que entre 8 y 10.
PRIOR_SATURATION = 4.0

# Grado de amenaza VM_05 → 0-1. "Muy alta" existe en algunas capas del POT.
_HAZARD_SCORES: dict[str, float] = {
    "muy alta": 1.0,
    "alta": 0.85,
    "media": 0.5,
    "moderada": 0.5,
    "baja": 0.15,
    "muy baja": 0.05,
    "sin amenaza": 0.0,
}


def _strip_accents(text: str) -> str:
    nkfd = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(c for c in nkfd if unicodedata.category(c) != "Mn")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_range(value: float | None, low: float, high: float) -> float | None:
    """Lleva `value` a 0-1 dentro de [low, high], saturando en los extremos."""
    if value is None:
        return None
    if high == low:
        return None
    return _clamp01((value - low) / (high - low))


def normalize_slope(slope_deg: float | None) -> float | None:
    return _normalize_range(slope_deg, SLOPE_MIN_DEG, SLOPE_MAX_DEG)


def normalize_twi(twi: float | None) -> float | None:
    return _normalize_range(twi, TWI_MIN, TWI_MAX)


def normalize_ndvi(ndvi_min: float | None) -> float | None:
    """NDVI → susceptibilidad. Invertido: menos vegetación, más susceptible."""
    if ndvi_min is None:
        return None
    return _normalize_range(-ndvi_min, -NDVI_DENSE, -NDVI_BARE)


def normalize_hazard_grade(grade: str | None) -> float | None:
    """Grado textual de VM_05 → 0-1. Grado desconocido → None, nunca 0.0.

    Devolver 0.0 ante un texto no reconocido diría "sin amenaza", que es lo
    contrario de "no tengo el dato".
    """
    if not grade or not grade.strip():
        return None
    key = _strip_accents(grade)
    if key in _HAZARD_SCORES:
        return _HAZARD_SCORES[key]
    # Coincidencia parcial: la capa a veces trae "Amenaza alta por movimientos…".
    # Se prueba de más específico a menos para que "muy alta" no case con "alta".
    for label in sorted(_HAZARD_SCORES, key=len, reverse=True):
        if label in key:
            return _HAZARD_SCORES[label]
    return None


def normalize_prior_events(n_events: float | None) -> float | None:
    """Nº de deslizamientos históricos inventariados → 0-1, saturante.

    ⚠️ Quien llame debe contar SOLO eventos anteriores a la fecha de referencia y
    excluir los sintéticos. La etiqueta de un modelo supervisado ES un evento, así
    que usar el histórico completo filtraría el objetivo. Aquí no se puede
    comprobar: es un contrato del llamador.
    """
    if n_events is None:
        return None
    if n_events <= 0:
        return 0.0
    return _clamp01(1.0 - 0.5 ** (n_events / PRIOR_SATURATION))


@dataclass(frozen=True)
class SusceptibilityBreakdown:
    """Índice y su desglose, para que el dashboard lo muestre auditable.

    `coverage` es la fracción de peso que sí tenía dato: un índice con
    coverage 0.25 es una conjetura, no una medición, y la UI debe poder decirlo.
    """

    index: float | None
    components: dict[str, float | None]
    weights_used: dict[str, float]
    coverage: float


_COMPONENT_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("slope", W_SLOPE),
    ("hazard", W_HAZARD),
    ("twi", W_TWI),
    ("prior", W_PRIOR),
    ("ndvi", W_NDVI),
)


def susceptibility_breakdown(
    *,
    slope_p90_deg: float | None = None,
    twi_p90: float | None = None,
    ndvi_min: float | None = None,
    hazard_grade: str | None = None,
    hazard_fraction: float | None = None,
    prior_event_count: float | None = None,
) -> SusceptibilityBreakdown:
    """Susceptibilidad estática 0-1, con desglose y cobertura.

    Los pesos se renormalizan sobre los componentes presentes, así que el índice
    es comparable entre zonas aunque unas tengan más datos que otras — pero
    `coverage` dice cuánta confianza merece.

    El componente de amenaza admite dos formas, y `hazard_fraction` tiene
    prioridad porque es una señal mejor:

    - `hazard_fraction` (0-1): fracción del área en amenaza alta, agregada sobre
      muchos polígonos (p. ej. los barrios de una comuna).
    - `hazard_grade` (texto): el grado de VM_05 en UN punto. Es el respaldo
      cuando no hay desagregación. Cuidado: muestrear en el centroide engaña —
      la comuna 1 (Popular, ladera nororiental) sale "Baja" en su centroide
      mientras 3 de sus 12 barrios están en amenaza Alta.
    """
    components: dict[str, float | None] = {
        "slope": normalize_slope(slope_p90_deg),
        "hazard": (
            _clamp01(hazard_fraction)
            if hazard_fraction is not None
            else normalize_hazard_grade(hazard_grade)
        ),
        "twi": normalize_twi(twi_p90),
        "prior": normalize_prior_events(prior_event_count),
        "ndvi": normalize_ndvi(ndvi_min),
    }

    total_weight = 0.0
    weighted_sum = 0.0
    weights_used: dict[str, float] = {}
    for name, weight in _COMPONENT_WEIGHTS:
        value = components[name]
        if value is None:
            continue
        weights_used[name] = weight
        total_weight += weight
        weighted_sum += weight * value

    if total_weight <= 0.0:
        return SusceptibilityBreakdown(None, components, {}, 0.0)

    index = _clamp01(weighted_sum / total_weight)
    # Los pesos que se reportan son los EFECTIVOS (ya renormalizados), que es lo
    # que hay que enseñar en un tooltip para que la suma cuadre.
    effective = {k: round(w / total_weight, 4) for k, w in weights_used.items()}
    return SusceptibilityBreakdown(
        index=round(index, 4),
        components=components,
        weights_used=effective,
        coverage=round(total_weight, 4),
    )


def susceptibility_index(**kwargs: float | str | None) -> float | None:
    """Atajo cuando solo hace falta el escalar."""
    return susceptibility_breakdown(**kwargs).index  # type: ignore[arg-type]


# ── Disparador (dinámico) ─────────────────────────────────────────────────────
#
# El SWI ya viene en 0-100 %, así que se divide. El índice antecedente de lluvia
# está en mm sin techo natural: se normaliza contra la referencia declarada en
# `risk_rules.ANTECEDENT_INDEX_THRESHOLD_MM`, que el llamador pasa.
SEISMIC_SATURATION = 30.0  # Σ mag²·atenuación·decaimiento que se considera "alto"

# El sismo MODULA, no dispara por sí solo: en Medellín el detonante dominante es
# la lluvia. Un sismo sobre suelo seco raramente mueve una ladera; sobre suelo
# saturado sí. Por eso el disparador es la lluvia realzada por la sismicidad, y
# no una media de las dos.
SEISMIC_MAX_BOOST = 0.35


def trigger_breakdown(
    *,
    soil_water_index_pct: float | None = None,
    antecedent_precip_mm: float | None = None,
    antecedent_reference_mm: float = 100.0,
    seismic_intensity: float | None = None,
) -> dict[str, float | None]:
    """Disparador 0-1 y sus partes.

    Lluvia = max(SWI, índice antecedente normalizado) — se toma el máximo, no la
    media, porque son dos formas de medir lo mismo (agua acumulada en el suelo) y
    promediarlas diluiría una señal alta con una baja.
    """
    swi = _clamp01(soil_water_index_pct / 100.0) if soil_water_index_pct is not None else None
    api = (
        _clamp01(antecedent_precip_mm / antecedent_reference_mm)
        if antecedent_precip_mm is not None and antecedent_reference_mm > 0
        else None
    )
    seismic = (
        _clamp01(seismic_intensity / SEISMIC_SATURATION) if seismic_intensity is not None else None
    )

    rain_parts = [v for v in (swi, api) if v is not None]
    rain = max(rain_parts) if rain_parts else None

    if rain is None:
        trigger = None
    else:
        boost = 1.0 + SEISMIC_MAX_BOOST * (seismic or 0.0)
        trigger = _clamp01(rain * boost)

    return {
        "trigger": round(trigger, 4) if trigger is not None else None,
        "rain": round(rain, 4) if rain is not None else None,
        "swi": swi,
        "antecedent": round(api, 4) if api is not None else None,
        "seismic": round(seismic, 4) if seismic is not None else None,
    }


def hazard_score(susceptibility: float | None, trigger: float | None) -> float | None:
    """Amenaza 0-1 = media GEOMÉTRICA de susceptibilidad y disparador.

    Media geométrica y no producto: el producto de dos valores 0-1 comprime hacia
    cero (0.5 × 0.5 = 0.25), así que con los umbrales vigentes
    (medio 0.35 / alto 0.65 / crítico 0.90) casi nunca se alcanzaría "crítico" y
    el índice sería inservible en la práctica. La media geométrica conserva la
    escala (0.5 y 0.5 → 0.5) manteniendo la propiedad física que importa: si
    CUALQUIERA de los dos factores es cero, la amenaza es cero. Sin disparador no
    hay deslizamiento; en terreno plano y estable, tampoco.

    Devuelve None si falta cualquiera de los dos: un score inventado es peor que
    la ausencia de score, sobre todo si alimenta una alerta a Gestión del Riesgo.
    """
    if susceptibility is None or trigger is None:
        return None
    return round((max(0.0, susceptibility) * max(0.0, trigger)) ** 0.5, 4)
