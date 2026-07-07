from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BarrioHazard(Base):
    """Grado de amenaza por movimientos en masa a nivel de BARRIO.

    Muestreado en el centroide de cada uno de los ~401 barrios de
    `barrios-medellin.json` contra la capa oficial de ordenamiento
    territorial VM_05_Amenazas_Movimientos_Masa (misma capa que ya se
    consulta a nivel de comuna en scraper/medellin_datos.py). Cartografía
    casi estática: se refresca con un script puntual, no con cron.
    """

    __tablename__ = "barrio_hazard"

    barrio_codigo: Mapped[str] = mapped_column(String(32), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    commune_id: Mapped[str] = mapped_column(String(64), index=True)
    hazard_grade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
