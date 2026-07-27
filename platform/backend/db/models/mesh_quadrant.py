from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class MeshQuadrant(Base):
    """Cuadrícula de ~1.5km² sobre Medellín (metodología JMA "Mesh Maps").

    Generada por `scraper/mesh_grid.py` (script puntual, cartografía casi
    estática) intersectando el grid con los 401 barrios de
    `barrios-medellin.json` y su `hazard_grade` (tabla `barrio_hazard`).

    IMPORTANTE — límite honesto: el riesgo de cada cuadrícula se HEREDA del
    modelo a nivel comuna (no hay sensores ni predicción por cuadrícula). El
    valor de esta capa es de visualización más precisa y evacuación dirigida,
    no de predicción más granular. Ver `risk_source` en la respuesta del API.
    """

    __tablename__ = "mesh_quadrants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "Q_0045"
    geometry: Mapped[dict[str, Any]] = mapped_column(JSONB)  # GeoJSON Polygon
    commune_ids: Mapped[list[str]] = mapped_column(JSONB)  # comunas que intersecta
    barrio_codigos: Mapped[list[str]] = mapped_column(JSONB)  # barrios que intersecta
    hazard_grade: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # peor grado entre sus barrios
    n_barrios_alta: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
