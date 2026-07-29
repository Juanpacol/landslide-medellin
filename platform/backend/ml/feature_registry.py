"""
Registro ÚNICO de las features del modelo. Declararlas aquí es lo único que
las mete (o las saca) del vector.

Por qué existe este módulo
--------------------------
La lista de claves vivía en DOS sitios y divergieron en silencio:

- el spread condicional de `scraper/siata.py` (qué se escribe en el JSONB), y
- el literal `force_keys` de `ml/train.py` (qué entra al vector).

El resultado quedó documentado en producción: `ml/models/feature_names.json`
lista 7 features y NINGUNA de las 4 de ingeniería (`antecedent_precip_index`,
`soil_water_index_pct`, `seismic_recent_intensity`, `pct_barrios_alta_amenaza`).
La corrida de 11 features que las incluía abortó el 2026-07-07 (`n_positive: 0`,
`target_strategy: past_7d_fallback` — ver `ml/models/last_train_attempt.json`) y
nunca se reprodujo. La gobernanza de artefactos de `train.py` hizo su trabajo y
protegió producción, pero nadie se enteró porque nada alertó.

De las 7 features en producción, 6 no son meteorología: `centroid_lat`/`_lon`
son identidad de comuna, `densidadmax` es estática, `precip_records` y
`station_count` son conteos de filas (proxy de QUÉ SCRAPER escribió la fila), y
`precip_sum_mm_day` solo lo escriben los scrapers históricos, así que en
inferencia se rellena por mediana con una constante rancia por comuna. Con 26
positivos, eso es un modelo que memoriza cuál de las 21 comunas tuvo eventos.

Presupuesto de columnas
-----------------------
Con 26 positivos reales y `max_depth=3`, el techo defendible son ~12-14
columnas. Añadir features es un juego de suma cero: para meter una hay que
justificar la que sale. `DENY_KEYS` es la mitad del trabajo, no un detalle.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    """Declaración de una feature. `key` es la clave en `MLFeature.features`."""

    key: str
    module: str  # dónde se calcula ("-" si la escribe un scraper directo)
    window_days: int | None  # None = estática o de instante
    descripcion: str
    in_model: bool = True
    forward_looking: bool = False  # mira al FUTURO → jamás entrena (ver §pronóstico)


REGISTRY: tuple[FeatureSpec, ...] = (
    # ── Lluvia ────────────────────────────────────────────────────────────────
    FeatureSpec(
        key="antecedent_precip_index",
        module="ml/precip_index.py",
        window_days=15,
        descripcion="Σ lluvia_d × 0.85^días_atrás. Saturación acumulada del suelo.",
    ),
    FeatureSpec(
        key="soil_water_index_pct",
        module="ml/soil_water_index.py",
        window_days=30,
        descripcion="Modelo de tanque: SWI = SWI×(1−0.15) + lluvia, tope 100.",
    ),
    FeatureSpec(
        key="mean_precip_mm_snapshot",
        module="scraper/siata.py",
        window_days=None,
        descripcion=(
            "Media de precipitación de las estaciones SIATA en el snapshot. "
            "PENDIENTE de retirar: ver DENY_KEYS_PENDIENTE_LLUVIA."
        ),
    ),
    FeatureSpec(
        key="precip_sum_mm_day",
        module="scraper/ideam.py, scraper/historical_backfill.py",
        window_days=1,
        descripcion=(
            "Suma diaria de precipitación. Solo la escriben los caminos "
            "históricos/IDEAM. PENDIENTE de retirar: ver DENY_KEYS_PENDIENTE_LLUVIA."
        ),
    ),
    # ── Sismos ────────────────────────────────────────────────────────────────
    FeatureSpec(
        key="seismic_recent_intensity",
        module="ml/seismic_features.py",
        window_days=30,
        descripcion="Σ magnitud² × 1/(1+(d/50)²) × 0.9^días.",
    ),
    FeatureSpec(
        key="seismic_x_swi",
        module="scraper/siata.py (interacción)",
        window_days=30,
        descripcion="seismic_recent_intensity × (SWI/100). Sismo sobre suelo saturado.",
    ),
    # ── Terreno / vulnerabilidad (estáticas) ──────────────────────────────────
    FeatureSpec(
        key="pct_barrios_alta_amenaza",
        module="ml/barrio_hazard_features.py",
        window_days=None,
        descripcion="% de barrios de la comuna en amenaza alta (VM_05 de GeoMedellín).",
    ),
    FeatureSpec(
        key="densidadmax",
        module="scraper/medellin_datos.py",
        window_days=None,
        descripcion=(
            "Densidad poblacional máxima. Estática por comuna, pero es "
            "vulnerabilidad legítima — no un identificador."
        ),
    ),
)

BY_KEY: dict[str, FeatureSpec] = {s.key: s for s in REGISTRY}


# ── Claves EXCLUIDAS del vector ───────────────────────────────────────────────
#
# Se siguen escribiendo en el JSONB (hay código que las lee: por ejemplo
# `ml/seismic_features.py::_centroids_by_commune` y
# `alerts/evacuation.py::_commune_centroid` leen los centroides). Lo que se
# impide es que lleguen a la matriz de entrenamiento.
DENY_KEYS: frozenset[str] = frozenset(
    {
        # Identidad de comuna: constante por comuna para siempre. Con 26
        # positivos el árbol memoriza cuál de las 21 comunas tuvo eventos.
        "centroid_lat",
        "centroid_lon",
        # Conteos de filas: proxy de QUÉ SCRAPER escribió la fila, no del clima.
        "precip_records",
        "station_count",
        # Siempre None en la BD (todos los scrapers la escriben así), así que
        # nunca llegó al vector; queda declarada para que rellenar la columna
        # más adelante no la meta al modelo por accidente. Además sería
        # `antecedent_precip_index` con decay=1.0 y ventana=7 → r > 0.95.
        # El propio docstring de precip_index.py ya dice "NO usar".
        "precip_acum_7d",
        "n_events_window",
    }
)

# Claves que DEBEN salir del vector, pero todavía no.
#
# `mean_precip_mm_snapshot` y `precip_sum_mm_day` son hoy la única señal de
# lluvia del modelo. Se sustituyen por la clave canónica `precip_daily_mm`
# (total diario resuelto por precedencia de fuentes), pero esa clave no existe
# hasta que `ml/backfill_features.py` la pueble sobre el histórico. Retirarlas
# ANTES de eso dejaría al modelo sin lluvia — peor que el problema.
#
# Activación: mover estas dos a DENY_KEYS en el mismo PR que introduce
# `precip_daily_mm`, y verificar con `feature_coverage["precip_daily_mm"] ≥ 0.95`.
DENY_KEYS_PENDIENTE_LLUVIA: frozenset[str] = frozenset(
    {
        "mean_precip_mm_snapshot",
        "precip_sum_mm_day",
    }
)

# Prefijos de claves que nunca entran al vector.
#   meta_*  metadatos de procedencia/salud de fuente (`meta_seismic_source_ok`)
#   fc_*    derivadas del PRONÓSTICO: miran al futuro y la etiqueta es "evento
#           en (ref_d, ref_d+7d]", así que entrenar con ellas filtra la causa
#           física de la etiqueta. Se usan en inferencia vía doble puntuación
#           (x_now / x_projected), nunca en entrenamiento.
DENY_PREFIXES: tuple[str, ...] = ("meta_", "fc_")


# Claves que se fuerzan a entrar al vector aunque ninguna fila las tenga
# todavía. Sin esto, la unión de claves observadas las descarta en silencio y
# la feature "existe" en el código pero nunca entrena — exactamente lo que
# pasó con las 4 de ingeniería.
FORCE_KEYS: frozenset[str] = frozenset(
    s.key for s in REGISTRY if s.in_model and not s.forward_looking
)


def is_denied(key: str) -> bool:
    """True si la clave no debe entrar al vector de features."""
    if key in DENY_KEYS:
        return True
    return key.startswith(DENY_PREFIXES)
