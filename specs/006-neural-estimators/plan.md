# SPEC-006 — plan.md

## Architecture

`ml/` layer, same position as today — I/O for training/inference, pure normalization delegated
to `domain/susceptibility.py` normalizers where applicable.

## Files touched

- `ml/estimators/__init__.py`, `ml/estimators/base.py` — `Signal`, `Estimator` protocol.
- `ml/estimators/xgboost_estimator.py`, `ml/estimators/rainfall_estimator.py`,
  `ml/estimators/seismic_estimator.py`, `ml/estimators/terrain_estimator.py`.
- `ml/feature_registry.py` — denylist enforcement.
- `ml/train.py` — collapse guard (Slack alert via existing `alerts/slack.py` conventions).
- `scraper/terrain_features.py` — new scraper, SRTM + MODIS ingestion into `barrio_terrain`.

## Interfaces

```python
@dataclass(frozen=True)
class Signal:
    value: float | None
    uncertainty: float
    source: str
    coverage: float

class Estimator(Protocol):
    def estimate(self, snapshot: TerritorySnapshot) -> Signal: ...
```

## Sequencing

Independent of SPEC-001..005; `scraper/terrain_features.py` (task 4) can start immediately — it
is the data prerequisite for SPEC-002's slope/TWI/NDVI rules to ever fire on real data.
