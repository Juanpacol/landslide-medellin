from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SeismicEvent(Base):
    """Reporte CRUDO de un sismo, tal como lo publicó su fuente.

    Una fila = un reporte, no un sismo. Un mismo sismo físico genera K filas de
    SIATA (una por estación que lo registró) más una por cada agencia
    (USGS, SGC). El sismo físico es `seismic_event_clusters`, al que apunta
    `cluster_id`; las features de ML leen clústeres, nunca esta tabla.

    Estas filas no se borran ni se mutan jamás: los números de cada agencia
    quedan auditables aunque el consenso del clúster cambie después.

    Fuentes:
    - `siata_sismos`: GeoJSON `ultimos_sismos_*.geojson` del geoportal de
      ingeniería sísmica de SIATA; cada estación publica hasta 3 eventos.
    - `usgs`: servicio FDSN, acotado por bounding box de Colombia.
    - `sgc`: Red Sismológica Nacional de Colombia.

    `source_row_id` es único a nivel GLOBAL, con las fuentes nuevas prefijadas
    (`"usgs:<id>"`, `"sgc:<id>"`). El formato de SIATA se deja intacto a
    propósito: prefijarlo haría que todos los eventos históricos parezcan nuevos
    y se reinsertaría la tabla completa en la siguiente corrida.
    """

    __tablename__ = "seismic_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_row_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="siata_sismos", index=True
    )
    # Nullable: SIATA es una red de estaciones, pero un evento de USGS o del SGC
    # es una solución de agencia y no tiene estación asociada.
    station_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    station_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nombre heredado. Es `DateTime(timezone=True)`, así que almacena el instante
    # correcto sea cual sea la zona de origen: SIATA publica hora de Bogotá,
    # USGS epoch ms en UTC. Quien escribe convierte a datetime tz-aware.
    event_local_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Escala de la magnitud, tal como la publica la fuente: el SGC usa
    # `MLr`/`MLr_1..4`/`MLr_vmm` (ML regional calibrada por región) y USGS `mb`
    # en los eventos colombianos. **No son comparables entre sí**: nunca
    # promediar magnitudes de fuentes distintas. Por eso la magnitud de consenso
    # del clúster es la del ganador de precedencia, no una media.
    mag_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    depth_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    epicenter_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sismo físico al que pertenece este reporte. NULL = todavía sin agrupar
    # (filas históricas hasta que corra `scraper/seismic_cluster_backfill.py`).
    cluster_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("seismic_event_clusters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
