from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.session import SyncSessionLocal, sync_engine  # noqa: E402
from ml.train import _build_supervised_matrix  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"
REPORT_PATH = MODELS_DIR / "report.md"
METRICS_PATH = MODELS_DIR / "metrics.json"
BEST_MODEL_PATH = MODELS_DIR / "best_model.pkl"


def _fmt(x: float | None) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/d"
    return f"{float(x):.4f}"


def generate_report() -> str:
    metrics: dict[str, Any] = {}
    if METRICS_PATH.exists():
        metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))

    lines: list[str] = [
        "# TEYVA ML evaluation report",
        "",
        "## Training metrics (CV / artifacts)",
        "",
        f"- Samples: **{metrics.get('n_samples', 'n/d')}**",
        f"- Positives (event in +7d): **{metrics.get('n_positive', 'n/d')}**",
        f"- Best model: **{metrics.get('best_model', 'n/d')}**",
        f"- Mean AUC-ROC (CV): **{_fmt(metrics.get('cv_mean_auc'))}**",
        f"- CV strategy: **{metrics.get('cv_strategy', 'n/d')}**",
        f"- AUC-ROC on the full dataset (fitted): **{_fmt(metrics.get('train_auc_roc'))}**",
        "",
    ]

    if not BEST_MODEL_PATH.exists():
        lines.append("_No `best_model.pkl`; run `python -m ml.train`._")
        text = "\n".join(lines)
        REPORT_PATH.write_text(text, encoding="utf-8")
        return text

    artifact = joblib.load(BEST_MODEL_PATH)
    model = artifact["model"]

    with SyncSessionLocal() as session:
        X, y, _names, _meta, _target_strategy, _coverage = _build_supervised_matrix(session)

    if X.size == 0 or len(np.unique(y)) < 2:
        lines.append("_Insufficient data or a single class for classification metrics._")
        text = "\n".join(lines)
        REPORT_PATH.write_text(text, encoding="utf-8")
        return text

    scaler = joblib.load(MODELS_DIR / "scaler.pkl")
    Xs = scaler.transform(X)
    proba = model.predict_proba(Xs)[:, 1]
    y_hat = (proba >= 0.5).astype(int)

    auc = float(roc_auc_score(y, proba))
    f1 = float(f1_score(y, y_hat, zero_division=0))
    prec = float(precision_score(y, y_hat, zero_division=0))
    rec = float(recall_score(y, y_hat, zero_division=0))
    acc = float(accuracy_score(y, y_hat))

    lines.extend(
        [
            "## Metrics on the full dataset (threshold 0.5)",
            "",
            f"- AUC-ROC: **{_fmt(auc)}**",
            f"- F1: **{_fmt(f1)}**",
            f"- Precision: **{_fmt(prec)}**",
            f"- Recall: **{_fmt(rec)}**",
            f"- Accuracy: **{_fmt(acc)}**",
            "",
            "_Note: evaluating on the same set used to fit the model makes "
            "these metrics optimistic; the primary generalization reference is the CV AUC-ROC in `metrics.json`._",
            "",
        ]
    )

    text = "\n".join(lines)
    REPORT_PATH.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    _ = sync_engine  # noqa: F841
    out = generate_report()
    print(out)


if __name__ == "__main__":
    main()
