from sqlalchemy import Column, DateTime, Float, String, text

from db.base import Base


class CommuneThreshold(Base):
    __tablename__ = "commune_thresholds"

    commune_id = Column(String(64), primary_key=True)
    threshold_mm = Column(Float, nullable=False, default=35.0)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))
