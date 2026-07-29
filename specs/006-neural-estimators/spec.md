# SPEC-006 — Neural Estimators

## Problem

The audit found 6 of 7 model features are near-constant per commune (identifier fingerprints),
and susceptibility today only has 1 of 5 declared components populated (`hazard_fraction`) — slope,
TWI and NDVI are defined in `domain/susceptibility.py` but never ingested into `barrio_terrain`.

## Goal

Each evidence source becomes an independent estimator with a common `Signal(value, uncertainty,
source, coverage)` protocol; XGBoost is demoted to one estimator among several, retrained without
identifier-like features; the terrain data gap is closed.

## Non-goals

- Solving the label problem (0 usable positives remains true; retraining reduces overfitting to
  commune identity, it does not create a valid supervised target).

## Acceptance criteria

1. `ml/estimators/` exposes one estimator per source with `estimate(snapshot) -> Signal`.
2. `ml/feature_registry.py` enforces a denylist excluding `centroid_lat/lon`, `densidadmax`,
   `precip_records`, `station_count` from training.
3. `ml/train.py` aborts with a Slack alert if the positive count collapses (the exact silent
   failure the audit documented).
4. `scraper/terrain_features.py` ingests SRTM slope/TWI and MODIS NDVI into `barrio_terrain`,
   raising susceptibility coverage from 1/5 to 4/5 components.
5. Tests: denylist enforced, every `Signal` has uncertainty populated, collapse guard fires on a
   synthetic 0-positive dataset.
