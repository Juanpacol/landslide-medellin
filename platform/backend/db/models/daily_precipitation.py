from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class DailyPrecipitation(Base):
    """Lluvia DIARIA por comuna y fuente.

    Existe aparte de `rainfall_timeseries` por una diferencia de grano que no se
    puede mezclar: SIATA escribe ~48 snapshots de 30 min por comuna y día,
    mientras que OWM/GPM/CHIRPS dan UN total para el día. Meterlos en la misma
    tabla rompería `GET /api/rain/live`, que suma `precip_mm` por snapshot.

    Varias fuentes pueden coexistir para el mismo (comuna, día) — la PK las
    admite a propósito. Cuál gana se decide al LEER, en
    `infrastructure/repositories/daily_rain.py`, con una escalera de precedencia
    y un invariante que tiene su propio test: **jamás se suman dos fuentes para
    el mismo (comuna, día)**. Sumarlas daría totales de lluvia inventados.
    """

    __tablename__ = "daily_precipitation"

    commune_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # "siata" | "owm_observed" | "gpm" | "chirps" | "ideam"
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    precip_mm: Mapped[float] = mapped_column(Float, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_daily_precip_day", "day"),)
