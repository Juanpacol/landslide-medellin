from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SeismicEvent(Base):
    """Sismo registrado por las estaciones SIATA (sismógrafos/acelerógrafos).

    Fuente: los GeoJSON `ultimos_sismos_*.geojson` del geoportal de ingeniería
    sísmica de SIATA. Cada estación publica hasta 3 eventos recientes; se
    deduplican por `source_row_id` (estación + fecha del evento).
    """

    __tablename__ = "seismic_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_row_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    station_code: Mapped[str] = mapped_column(String(32))
    station_name: Mapped[str] = mapped_column(Text)
    event_local_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
