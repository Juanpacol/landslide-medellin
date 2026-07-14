from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class MLFeature(Base):
    __tablename__ = "ml_features"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(64), index=True)
    reference_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    precip_acum_7d: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_events_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
