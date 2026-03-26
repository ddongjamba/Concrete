from datetime import datetime
from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    id: str
    inspection_id: str
    status: str           # queued | running | completed | failed
    progress_pct: int
    model_version: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class BoundingBox(BaseModel):
    x: float   # center x (normalized 0-1)
    y: float   # center y (normalized 0-1)
    w: float   # width (normalized)
    h: float   # height (normalized)


class AnalysisResultResponse(BaseModel):
    id: str
    job_id: str
    inspection_file_id: str
    defect_type: str
    severity_score: int          # 0-100
    severity: str                # low | medium | high | critical
    confidence: float
    bounding_box: BoundingBox
    crack_width_mm: float | None
    crack_length_mm: float | None
    crack_area_cm2: float | None
    affected_area_pct: float | None
    annotated_image_url: str | None  # presigned GET URL (1시간 유효)
    created_at: datetime


class AnalysisResultListResponse(BaseModel):
    items: list[AnalysisResultResponse]
    total: int
    summary: dict   # {total, by_severity: {low, medium, high, critical}}
