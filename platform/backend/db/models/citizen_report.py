from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class CitizenReport(Base):
    """Avistamiento reportado por un ciudadano vía el chatbot.

    Tabla SEPARADA de `landslide_events` (eventos oficiales DAGRD) a
    propósito: un reporte ciudadano nace sin verificar y NO debe alimentar
    el entrenamiento del modelo ni disparar alertas hasta que un operario
    lo marque `verified`. Flujo de estados:
    pending_review → verified | rejected.
    """

    __tablename__ = "citizen_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commune_id: Mapped[str] = mapped_column(String(64), index=True)
    barrio: Mapped[str | None] = mapped_column(Text, nullable=True)
    descripcion: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitud: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
