"""Tests puros de application/predict_risk.py::_veto_log_rows. Sin BD — solo construcción
de filas a partir de un Verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from application.predict_risk import _veto_log_rows
from db.models.veto_log import VetoLog


@dataclass(frozen=True)
class _FakeVerdict:
    derivation: dict[str, Any] = field(default_factory=dict)
    conflicts: tuple[dict[str, Any], ...] = ()


RUN_AT = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


class TestVetoLogRows:
    def test_no_rows_when_not_vetoed(self):
        verdict = _FakeVerdict(derivation={"vetoed": False}, conflicts=())
        assert _veto_log_rows("8", verdict, run_at=RUN_AT) == []

    def test_one_row_per_veto_conflict(self):
        verdict = _FakeVerdict(
            derivation={"vetoed": True, "neural_score": 0.42},
            conflicts=(
                {
                    "rule_id": "R-QUAL-01",
                    "effect": "veto",
                    "reason": "no_trigger_signal",
                    "neural_level": "medio",
                },
            ),
        )
        rows = _veto_log_rows("8", verdict, run_at=RUN_AT)
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, VetoLog)
        assert row.commune_id == "8"
        assert row.run_at == RUN_AT
        assert row.rule_id == "R-QUAL-01"
        assert row.reason == "no_trigger_signal"
        assert row.neural_level == "medio"
        assert row.neural_score == 0.42

    def test_non_veto_conflicts_are_excluded(self):
        verdict = _FakeVerdict(
            derivation={"vetoed": True},
            conflicts=(
                {"rule_id": "R-GEO-01", "effect": "set_floor"},
                {"rule_id": "R-QUAL-02", "effect": "veto", "reason": "corrupted_rain_signal"},
            ),
        )
        rows = _veto_log_rows("3", verdict, run_at=RUN_AT)
        assert len(rows) == 1
        assert rows[0].rule_id == "R-QUAL-02"

    def test_multiple_veto_conflicts_produce_multiple_rows(self):
        verdict = _FakeVerdict(
            derivation={"vetoed": True},
            conflicts=(
                {"rule_id": "R-QUAL-01", "effect": "veto", "reason": "no_trigger_signal"},
                {"rule_id": "R-QUAL-02", "effect": "veto", "reason": "corrupted_rain_signal"},
            ),
        )
        rows = _veto_log_rows("15", verdict, run_at=RUN_AT)
        assert {r.rule_id for r in rows} == {"R-QUAL-01", "R-QUAL-02"}

    def test_missing_reason_defaults_to_unknown(self):
        verdict = _FakeVerdict(
            derivation={"vetoed": True},
            conflicts=({"rule_id": "R-QUAL-01", "effect": "veto"},),
        )
        rows = _veto_log_rows("1", verdict, run_at=RUN_AT)
        assert rows[0].reason == "unknown"
