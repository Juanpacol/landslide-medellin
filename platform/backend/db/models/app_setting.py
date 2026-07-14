from sqlalchemy import Column, DateTime, String, Text, text

from db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"))
