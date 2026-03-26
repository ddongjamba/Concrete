import uuid
from sqlalchemy import String, Text, Enum, ForeignKey, DateTime, Integer, BigInteger, Numeric, Date
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase
from datetime import datetime, date
import enum


class InspectionStatus(str, enum.Enum):
    pending = "pending"
    uploading = "uploading"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class FileType(str, enum.Enum):
    image = "image"
    video = "video"


class Inspection(UUIDBase):
    __tablename__ = "inspections"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    drone_model: Mapped[str | None] = mapped_column(String(100))
    flight_altitude_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    inspection_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[InspectionStatus] = mapped_column(Enum(InspectionStatus), default=InspectionStatus.pending)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped["Project"] = relationship(back_populates="inspections")
    files: Mapped[list["InspectionFile"]] = relationship(back_populates="inspection")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="inspection")


class InspectionFile(UUIDBase):
    __tablename__ = "inspection_files"

    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(500))
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[FileType] = mapped_column(Enum(FileType))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # GPS / camera metadata for GSD calculation
    gps_lat: Mapped[float | None] = mapped_column(Numeric(10, 7))
    gps_lon: Mapped[float | None] = mapped_column(Numeric(10, 7))
    altitude_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    focal_length_mm: Mapped[float | None] = mapped_column(Numeric(8, 3))
    sensor_width_mm: Mapped[float | None] = mapped_column(Numeric(8, 3))
    image_width_px: Mapped[int | None] = mapped_column(Integer)

    inspection: Mapped["Inspection"] = relationship(back_populates="files")
