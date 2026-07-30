from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class VetoLog(Base):
    """Append-only record of every `Veto` a rule fired during inference
    (`application/neurosymbolic/infer.py`). `risk_predictions.raw_output` already carries this
    inside its JSONB `derivation`/`conflicts`, but auditing "how often and why did the system
    say I don't know" against a JSONB blob per commune-run is impractical — this is that same
    data flattened into a queryable table, one row per fired veto."""

    __tablename__ = "veto_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    # What the neural score alone would have resolved to, had the veto not overridden it —
    # lets a reader see what confidence was withheld from, not just that it was withheld.
    neural_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    neural_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
