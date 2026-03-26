import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase


class DefectAlert(UUIDBase):
    """앱 내 균열 악화 알림"""
    __tablename__ = "defect_alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("defect_tracks.id"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), default="worsening")  # worsening | new_crack | repaired
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
