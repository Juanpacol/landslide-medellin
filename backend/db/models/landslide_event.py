from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LandslideEvent(Base):
    __tablename__ = "landslide_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_row_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_emergencia: Mapped[str | None] = mapped_column(Text, nullable=True)
    commune_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    barrio: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_coords: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
