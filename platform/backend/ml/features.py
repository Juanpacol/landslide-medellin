from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.models.ml_feature import MLFeature
from ml.feature_registry import is_denied

ML_DIR = Path(__file__).resolve().parent
MODELS_DIR = ML_DIR / "models"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
FEATURE_NAMES_PATH = MODELS_DIR / "feature_names.json"

# Non-numeric JSON keys / identifiers that never enter the vector.
_SKIP_JSON_KEYS = frozenset(
    {
        "source",
        "nombre",
        "official_codigo",
        "station_codes",
        "barrios",
        "tratamiento",
        "geomedellin_hub",
        "socrata_dataset",
        "siata_json_url",
    }
)


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, (list, dict)):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ".").strip())
        except ValueError:
            return None
    return None


def _numeric_from_json(features: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not features:
        return out
    for k, v in features.items():
        if k in _SKIP_JSON_KEYS or is_denied(k):
            continue
        fv = _coerce_float(v)
        if fv is not None:
            out[k] = fv
    return out


def row_to_numeric_parts(row: MLFeature) -> dict[str, float]:
    """Numeric keys for a row, already filtered by the deny-list.

    `precip_acum_7d` and `n_events_window` are table columns, not from the
    JSONB, so they go through `is_denied` explicitly: both are in
    DENY_KEYS and must not enter the vector even once they get populated.
    """
    parts = _numeric_from_json(row.features or {})
    if row.precip_acum_7d is not None and not is_denied("precip_acum_7d"):
        parts["precip_acum_7d"] = float(row.precip_acum_7d)
    if row.n_events_window is not None and not is_denied("n_events_window"):
        parts["n_events_window"] = float(row.n_events_window)
    return parts


def _median_map(values_by_key: dict[str, list[float]]) -> dict[str, float]:
    medians: dict[str, float] = {}
    for k, vals in values_by_key.items():
        if not vals:
            continue
        medians[k] = float(np.median(np.array(vals, dtype=float)))
    return medians


class FeatureBuilder:
    """Builds per-commune feature vectors from `ml_features`."""

    def __init__(self, models_dir: Path | None = None) -> None:
        self.models_dir = models_dir or MODELS_DIR
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def scaler_path(self) -> Path:
        """Path of the persisted scaler for this builder's models_dir."""
        return self.models_dir / "scaler.pkl"

    def feature_names_path(self) -> Path:
        """Path of the persisted feature-name order for this builder's models_dir."""
        return self.models_dir / "feature_names.json"

    def collect_rows_sync(self, session: Session, commune_id: str) -> list[MLFeature]:
        """Fetches a commune's `ml_features` rows, most recent first (sync session)."""
        stmt = (
            select(MLFeature)
            .where(MLFeature.commune_id == str(commune_id))
            .order_by(MLFeature.reference_date.desc().nulls_last(), MLFeature.id.desc())
        )
        return list(session.scalars(stmt).all())

    async def collect_rows_async(self, session: AsyncSession, commune_id: str) -> list[MLFeature]:
        """Fetches a commune's `ml_features` rows, most recent first (async session)."""
        stmt = (
            select(MLFeature)
            .where(MLFeature.commune_id == str(commune_id))
            .order_by(MLFeature.reference_date.desc().nulls_last(), MLFeature.id.desc())
        )
        result = await session.scalars(stmt)
        return list(result.all())

    def _per_row_numeric_parts(self, rows: list[MLFeature]) -> list[dict[str, float]]:
        """Numeric parts per row, in the same order as `rows`."""
        return [row_to_numeric_parts(r) for r in rows]

    def _values_by_key(self, parts_list: list[dict[str, float]]) -> dict[str, list[float]]:
        """Groups each key's values across all rows, for median imputation."""
        acc: dict[str, list[float]] = defaultdict(list)
        for parts in parts_list:
            for k, v in parts.items():
                acc[k].append(v)
        return acc

    def merge_with_median_impute(
        self,
        rows: list[MLFeature],
        *,
        feature_order: list[str] | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """
        Takes the most recent value per key; if missing in the most recent
        row, uses that commune's historical median for that key.
        Returns (features_used, raw_vector aligned to feature_order).
        """
        if not rows:
            return {}, {}

        parts_list = self._per_row_numeric_parts(rows)
        medians = _median_map(self._values_by_key(parts_list))

        # Preferred values: from the most recent row (index 0) backward.
        merged: dict[str, float] = {}
        keys_union: set[str] = set()
        for p in parts_list:
            keys_union |= set(p.keys())

        for k in sorted(keys_union):
            val: float | None = None
            for p in parts_list:
                if k in p:
                    val = p[k]
                    break
            if val is None:
                val = medians.get(k, 0.0)
            merged[k] = float(val)

        order = feature_order if feature_order is not None else sorted(merged.keys())
        raw_aligned: dict[str, float] = {}
        for k in order:
            raw_aligned[k] = float(merged.get(k, medians.get(k, 0.0)))
        return merged, raw_aligned

    async def build_feature_vector(
        self,
        comuna_id: str | int,
        db: AsyncSession,
        *,
        feature_order: list[str] | None = None,
        apply_scaler: bool = True,
    ) -> dict[str, Any]:
        """Builds a commune's raw and (optionally) scaled feature vector for inference."""
        rows = await self.collect_rows_async(db, str(comuna_id))
        merged, raw_aligned = self.merge_with_median_impute(rows, feature_order=feature_order)

        order = feature_order if feature_order is not None else sorted(merged.keys())
        x = np.array([[raw_aligned.get(k, 0.0) for k in order]], dtype=float)

        scaled_row: list[float] | None = None
        scaler_path = self.scaler_path()
        if apply_scaler and scaler_path.exists():
            scaler = joblib.load(scaler_path)
            x_scaled = scaler.transform(x)
            scaled_row = x_scaled[0].tolist()

        return {
            "features_used": merged,
            "feature_order": order,
            "vector_raw": raw_aligned,
            "vector_scaled": scaled_row,
        }

    @staticmethod
    def save_scaler(scaler: Any, path: Path | None = None) -> Path:
        """Persists the `StandardScaler` (or another) with joblib."""
        target = path or SCALER_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(scaler, target)
        return target

    @staticmethod
    def save_feature_names(names: list[str], path: Path | None = None) -> Path:
        """Persists the feature name order used to build the training matrix."""
        target = path or FEATURE_NAMES_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(names, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def load_feature_names(path: Path | None = None) -> list[str]:
        """Loads the persisted feature name order, or `[]` if not yet saved."""
        target = path or FEATURE_NAMES_PATH
        if not target.exists():
            return []
        return json.loads(target.read_text(encoding="utf-8"))
