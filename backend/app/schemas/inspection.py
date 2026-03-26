from datetime import datetime, date
from pydantic import BaseModel


class InspectionCreate(BaseModel):
    label: str | None = None
    drone_model: str | None = None
    flight_altitude_m: float | None = None
    inspection_date: date | None = None


class InspectionUpdate(BaseModel):
    label: str | None = None
    drone_model: str | None = None
    flight_altitude_m: float | None = None
    inspection_date: date | None = None


class InspectionResponse(BaseModel):
    id: str
    project_id: str
    tenant_id: str
    label: str | None
    drone_model: str | None
    flight_altitude_m: float | None
    inspection_date: date | None
    status: str
    file_count: int
    total_size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True


class InspectionListResponse(BaseModel):
    items: list[InspectionResponse]
    total: int


# 파일 업로드
class FileUploadRequest(BaseModel):
    filename: str
    content_type: str          # image/jpeg, image/png, video/mp4 등
    size_bytes: int
    # 드론 EXIF 메타데이터 (선택)
    gps_lat: float | None = None
    gps_lon: float | None = None
    altitude_m: float | None = None
    focal_length_mm: float | None = None
    sensor_width_mm: float | None = None
    image_width_px: int | None = None


class FileUploadResponse(BaseModel):
    file_id: str
    presigned_url: str         # 프론트엔드가 이 URL로 직접 PUT 업로드
    storage_key: str


class FileConfirmRequest(BaseModel):
    file_ids: list[str]        # 업로드 완료된 파일 ID 목록


class FileConfirmResponse(BaseModel):
    inspection_id: str
    job_id: str                # Celery 태스크 ID (진행률 폴링용)
    status: str
