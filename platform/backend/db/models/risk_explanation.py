from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RiskExplanation(Base):
    __tablename__ = "risk_explanations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_category: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    generated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="template")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_risk_explanation_commune_at", "commune_id", "generated_at"),)
