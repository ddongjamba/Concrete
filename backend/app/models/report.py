import uuid
from sqlalchemy import String, Enum, ForeignKey, DateTime, SmallInteger
from sqlalchemy.orm import mapped_column, Mapped
from app.models.base import UUIDBase
from datetime import datetime
import enum


class ReportStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"


class Report(UUIDBase):
    __tablename__ = "reports"

    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(SmallInteger, default=1)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.pending)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
