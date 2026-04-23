from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(64), index=True)
    risk_score: Mapped[float] = mapped_column(Float)
    risk_category: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
