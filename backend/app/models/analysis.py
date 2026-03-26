import uuid
from sqlalchemy import String, Enum, ForeignKey, DateTime, SmallInteger, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase
from datetime import datetime
import enum


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class DefectType(str, enum.Enum):
    crack = "crack"
    spalling = "spalling"
    efflorescence = "efflorescence"
    stain = "stain"
    delamination = "delamination"
    other = "other"


class SeverityLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AnalysisJob(UUIDBase):
    __tablename__ = "analysis_jobs"

    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    model_version: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inspection: Mapped["Inspection"] = relationship(back_populates="analysis_jobs")
    results: Mapped[list["AnalysisResult"]] = relationship(back_populates="job")


class AnalysisResult(UUIDBase):
    __tablename__ = "analysis_results"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    inspection_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspection_files.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    defect_type: Mapped[DefectType] = mapped_column(Enum(DefectType))
    # Quantified metrics
    severity_score: Mapped[int] = mapped_column(SmallInteger, default=0)   # 0-100
    severity: Mapped[SeverityLevel] = mapped_column(Enum(SeverityLevel))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    bounding_box: Mapped[dict] = mapped_column(JSONB)                       # {x, y, w, h} normalized 0-1
    crack_width_mm: Mapped[float | None] = mapped_column(Numeric(8, 3))
    crack_length_mm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    crack_area_cm2: Mapped[float | None] = mapped_column(Numeric(12, 4))
    affected_area_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    annotated_image_key: Mapped[str | None] = mapped_column(String(1000))
    segmentation_mask_key: Mapped[str | None] = mapped_column(String(1000))
    metadata: Mapped[dict | None] = mapped_column(JSONB)

    job: Mapped["AnalysisJob"] = relationship(back_populates="results")
    track_entry: Mapped["DefectTrackEntry | None"] = relationship(back_populates="analysis_result")
