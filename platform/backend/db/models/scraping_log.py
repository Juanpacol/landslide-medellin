from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_downloaded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_valid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_discarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
