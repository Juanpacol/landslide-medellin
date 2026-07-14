from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String, text

from db.base import Base


class AlertLog(Base):
    __tablename__ = "alert_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    commune_id = Column(String(64), nullable=False, index=True)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    precip_acum_mm = Column(Float, nullable=True)
    threshold_mm = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    risk_category = Column(String(32), nullable=True)
    webhook_url = Column(String, nullable=True)
    status = Column(String(32), nullable=True)  # sent | failed | cooldown
    response_code = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
