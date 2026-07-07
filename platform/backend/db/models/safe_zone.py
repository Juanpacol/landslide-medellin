from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SafeZone(Base):
    """Candidato a zona segura de evacuación (parque, colegio, estadio).

    Poblada por `alerts/evacuation.py::fetch_safe_zones_osm()` consultando la
    Overpass API de OpenStreetMap — gratuita, sin key. MVP sin validar: no ha
    sido confirmada por Defensoría/DAGRD como punto de encuentro oficial, solo
    es un candidato geográfico razonable (parque/colegio/estadio existente).
    """

    __tablename__ = "safe_zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "osm_way_12345"
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(32))  # park | school | stadium
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    validated: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
