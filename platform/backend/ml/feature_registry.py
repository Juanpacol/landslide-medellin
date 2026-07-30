"""
SINGLE registry of the model's features. Declaring one here is the only
thing that puts it (or takes it out of) the vector.

Why this module exists
-----------------------
The key list used to live in TWO places and diverged silently:

- `scraper/siata.py`'s conditional spread (what gets written to the JSONB), and
- `ml/train.py`'s `force_keys` literal (what enters the vector).

The result was documented in production: `ml/models/feature_names.json`
lists 7 features and NONE of the 4 engineered ones
(`antecedent_precip_index`, `soil_water_index_pct`,
`seismic_recent_intensity`, `pct_barrios_alta_amenaza`). The 11-feature run
that included them aborted on 2026-07-07 (`n_positive: 0`,
`target_strategy: past_7d_fallback` — see `ml/models/last_train_attempt.json`)
and never reran. `train.py`'s artifact governance did its job and
protected production, but nobody found out because nothing alerted.

Of the 7 production features, 6 aren't weather: `centroid_lat`/`_lon` are
commune identity, `densidadmax` is static, `precip_records` and
`station_count` are row counts (a proxy for WHICH SCRAPER wrote the row),
and `precip_sum_mm_day` is only written by the historical scrapers, so at
inference time it's median-filled with a stale per-commune constant. With
26 positives, that's a model that memorizes which of the 21 communes had
events.

Column budget
--------------
With 26 real positives and `max_depth=3`, the defensible ceiling is ~12-14
columns. Adding features is a zero-sum game: to add one, you must justify
which one leaves. `DENY_KEYS` is half the work, not a detail.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    """Declaration of a feature. `key` is the key in `MLFeature.features`."""

    key: str
    module: str  # where it's computed ("-" if a scraper writes it directly)
    window_days: int | None  # None = static or instantaneous
    descripcion: str
    in_model: bool = True
    forward_looking: bool = False  # looks into the FUTURE → never trains (see §forecast)


REGISTRY: tuple[FeatureSpec, ...] = (
    # ── Rain ──────────────────────────────────────────────────────────────────
    FeatureSpec(
        key="antecedent_precip_index",
        module="ml/precip_index.py",
        window_days=15,
        descripcion="Σ rain_d × 0.85^days_back. Accumulated soil saturation.",
    ),
    FeatureSpec(
        key="soil_water_index_pct",
        module="ml/soil_water_index.py",
        window_days=30,
        descripcion="Tank model: SWI = SWI×(1−0.15) + rain, capped at 100.",
    ),
    FeatureSpec(
        key="mean_precip_mm_snapshot",
        module="scraper/siata.py",
        window_days=None,
        descripcion=(
            "Mean precipitation across SIATA stations in the snapshot. "
            "PENDING removal: see DENY_KEYS_PENDIENTE_LLUVIA."
        ),
    ),
    FeatureSpec(
        key="precip_sum_mm_day",
        module="scraper/ideam.py, scraper/historical_backfill.py",
        window_days=1,
        descripcion=(
            "Daily precipitation sum. Only written by the historical/IDEAM "
            "paths. PENDING removal: see DENY_KEYS_PENDIENTE_LLUVIA."
        ),
    ),
    # ── Seismic ───────────────────────────────────────────────────────────────
    FeatureSpec(
        key="seismic_recent_intensity",
        module="ml/seismic_features.py",
        window_days=30,
        descripcion="Σ magnitude² × 1/(1+(d/50)²) × 0.9^days.",
    ),
    FeatureSpec(
        key="seismic_x_swi",
        module="scraper/siata.py (interaction)",
        window_days=30,
        descripcion="seismic_recent_intensity × (SWI/100). Earthquake on saturated soil.",
    ),
    # ── Terrain / vulnerability (static) ────────────────────────────────────────
    FeatureSpec(
        key="pct_barrios_alta_amenaza",
        module="ml/barrio_hazard_features.py",
        window_days=None,
        descripcion="% of the commune's barrios in high hazard (GeoMedellín's VM_05).",
    ),
    FeatureSpec(
        key="densidadmax",
        module="scraper/medellin_datos.py",
        window_days=None,
        descripcion=(
            "Maximum population density. Static per commune, but a "
            "legitimate vulnerability signal — not an identifier."
        ),
    ),
)

BY_KEY: dict[str, FeatureSpec] = {s.key: s for s in REGISTRY}


# ── Keys EXCLUDED from the vector ──────────────────────────────────────────────
#
# Still written to the JSONB (there's code that reads them: e.g.
# `ml/seismic_features.py::_centroids_by_commune` and
# `alerts/evacuation.py::_commune_centroid` read the centroids). What's
# prevented is them reaching the training matrix.
DENY_KEYS: frozenset[str] = frozenset(
    {
        # Commune identity: constant per commune forever. With 26
        # positives the tree memorizes which of the 21 communes had events.
        "centroid_lat",
        "centroid_lon",
        # Row counts: a proxy for WHICH SCRAPER wrote the row, not the weather.
        "precip_records",
        "station_count",
        # Always None in the DB (every scraper writes it that way), so it
        # never reached the vector; kept declared so backfilling the column
        # later doesn't feed the model by accident. It would also be
        # `antecedent_precip_index` with decay=1.0 and window=7 → r > 0.95.
        # precip_index.py's own docstring already says "do NOT use".
        "precip_acum_7d",
        "n_events_window",
    }
)

# Keys that MUST leave the vector, but not yet.
#
# `mean_precip_mm_snapshot` and `precip_sum_mm_day` are today the model's
# only rain signal. They get replaced by the canonical `precip_daily_mm` key
# (daily total resolved by source precedence), but that key doesn't exist
# until `ml/backfill_features.py` populates it over the historical data.
# Removing them BEFORE that would leave the model with no rain at all —
# worse than the problem.
#
# Activation: move these two to DENY_KEYS in the same PR that introduces
# `precip_daily_mm`, and verify with `feature_coverage["precip_daily_mm"] ≥ 0.95`.
DENY_KEYS_PENDIENTE_LLUVIA: frozenset[str] = frozenset(
    {
        "mean_precip_mm_snapshot",
        "precip_sum_mm_day",
    }
)

# Key prefixes that never enter the vector.
#   meta_*  source provenance/health metadata (`meta_seismic_source_ok`)
#   fc_*    derived from the FORECAST: they look into the future and the
#           label is "event within (ref_d, ref_d+7d]", so training with
#           them leaks the label's physical cause. Used at inference via
#           double scoring (x_now / x_projected), never at training time.
DENY_PREFIXES: tuple[str, ...] = ("meta_", "fc_")


# Keys forced into the vector even if no row has them yet. Without this,
# the union of observed keys silently drops them and the feature "exists"
# in code but never trains — exactly what happened with the 4 engineered
# ones.
FORCE_KEYS: frozenset[str] = frozenset(
    s.key for s in REGISTRY if s.in_model and not s.forward_looking
)


def is_denied(key: str) -> bool:
    """True if the key must not enter the feature vector."""
    if key in DENY_KEYS:
        return True
    return key.startswith(DENY_PREFIXES)
