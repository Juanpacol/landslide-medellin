from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AuditLog(Base):
    """Registro append-only de acciones sensibles (cambios de umbral, webhook,
    predicciones manuales, reportes). No se actualiza ni borra desde la app:
    la trazabilidad es el punto."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Quién: rol autenticado + IP (no hay usuarios individuales todavía).
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    # Qué: verbo corto, ej. "set_threshold", "save_webhook", "predict_all".
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Sobre qué: ej. "commune:8", "app_setting:slack_webhook_url".
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # SHA-256 del payload (no el payload crudo: puede contener secretos como
    # URLs de webhook) + un resumen legible sin datos sensibles.
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
