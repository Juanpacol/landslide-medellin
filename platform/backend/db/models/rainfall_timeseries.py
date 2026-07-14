from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String

from db.base import Base


class RainfallTimeseries(Base):
    __tablename__ = "rainfall_timeseries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    commune_id = Column(String(64), nullable=False)
    snapshot_at = Column(DateTime(timezone=True), nullable=False)
    precip_mm = Column(Float, nullable=False)
    station_count = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_rainfall_ts_commune_snap", "commune_id", "snapshot_at", unique=True),
    )
