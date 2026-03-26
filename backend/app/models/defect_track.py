import uuid
from datetime import date, datetime
from sqlalchemy import String, Enum, ForeignKey, Date, DateTime, SmallInteger, Numeric
from app.models.compat import JsonType as JSONB
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase
import enum


class TrackStatus(str, enum.Enum):
    monitoring = "monitoring"
    worsening = "worsening"
    stable = "stable"
    repaired = "repaired"


class DefectTrack(UUIDBase):
    """균열의 생애 기록 — 건물(project)별로 동일 균열을 시계열 추적"""
    __tablename__ = "defect_tracks"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    first_seen_at: Mapped[date | None] = mapped_column(Date)
    location_zone: Mapped[str | None] = mapped_column(String(100))  # 예: "북측-3층-A"
    representative_image_key: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[TrackStatus] = mapped_column(Enum(TrackStatus), default=TrackStatus.monitoring)

    project: Mapped["Project"] = relationship(back_populates="defect_tracks")
    entries: Mapped[list["DefectTrackEntry"]] = relationship(back_populates="track", order_by="DefectTrackEntry.inspection_date")


class DefectTrackEntry(UUIDBase):
    """점검마다 해당 균열의 측정값 스냅샷"""
    __tablename__ = "defect_track_entries"

    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("defect_tracks.id"), nullable=False, index=True)
    analysis_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_results.id"), unique=True)
    inspection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    inspection_date: Mapped[date | None] = mapped_column(Date, index=True)
    severity_score: Mapped[int] = mapped_column(SmallInteger, default=0)   # 0-100
    crack_width_mm: Mapped[float | None] = mapped_column(Numeric(8, 3))
    crack_length_mm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    crack_area_cm2: Mapped[float | None] = mapped_column(Numeric(12, 4))
    # 이전 점검 대비 변화량: {width_delta, length_delta, score_delta}
    change_vs_prev: Mapped[dict | None] = mapped_column(JSONB)
    annotated_image_key: Mapped[str | None] = mapped_column(String(1000))

    track: Mapped["DefectTrack"] = relationship(back_populates="entries")
    analysis_result: Mapped["AnalysisResult | None"] = relationship(back_populates="track_entry")
