import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.inspection import Inspection, InspectionFile, InspectionStatus, FileType
from app.models.project import Project
from app.models.user import User
from app.schemas.inspection import (
    InspectionCreate, InspectionUpdate, InspectionResponse, InspectionListResponse,
    FileUploadRequest, FileUploadResponse, FileConfirmRequest, FileConfirmResponse,
)
from app.services.storage_service import StorageService
from app.services.analysis_service import enqueue_analysis

router = APIRouter()


# ── 점검 CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=InspectionListResponse)
async def list_inspections(
    project_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    await _get_project_or_404(project_id, user.tenant_id, db)

    base_q = select(Inspection).where(
        Inspection.project_id == uuid.UUID(project_id),
        Inspection.tenant_id == user.tenant_id,
        Inspection.deleted_at.is_(None),
    )
    total = await db.scalar(select(func.count()).select_from(base_q.subquery()))
    result = await db.execute(base_q.order_by(Inspection.created_at.desc()).offset(skip).limit(limit))
    return InspectionListResponse(
        items=[_to_response(i) for i in result.scalars().all()],
        total=total or 0,
    )


@router.post("", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    project_id: str,
    body: InspectionCreate,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_project_or_404(project_id, user.tenant_id, db)

    inspection = Inspection(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        tenant_id=user.tenant_id,
        created_by=user.id,
        **body.model_dump(),
    )
    db.add(inspection)
    await db.commit()
    await db.refresh(inspection)
    return _to_response(inspection)


@router.get("/{inspection_id}", response_model=InspectionResponse)
async def get_inspection(
    project_id: str,
    inspection_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return _to_response(await _get_inspection_or_404(inspection_id, project_id, user.tenant_id, db))


@router.patch("/{inspection_id}", response_model=InspectionResponse)
async def update_inspection(
    project_id: str,
    inspection_id: str,
    body: InspectionUpdate,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    inspection = await _get_inspection_or_404(inspection_id, project_id, user.tenant_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(inspection, field, value)
    await db.commit()
    await db.refresh(inspection)
    return _to_response(inspection)


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(
    project_id: str,
    inspection_id: str,
    user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    inspection = await _get_inspection_or_404(inspection_id, project_id, user.tenant_id, db)
    inspection.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── 파일 업로드 ───────────────────────────────────────────────────────────────

@router.post("/{inspection_id}/files", response_model=FileUploadResponse)
async def request_upload(
    project_id: str,
    inspection_id: str,
    body: FileUploadRequest,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    presigned PUT URL 발급.
    프론트엔드는 이 URL로 직접 MinIO/S3에 파일을 PUT 업로드한다.
    """
    inspection = await _get_inspection_or_404(inspection_id, project_id, user.tenant_id, db)

    file_type = FileType.video if body.content_type.startswith("video/") else FileType.image
    storage_key = f"{user.tenant_id}/{inspection_id}/{uuid.uuid4()}/{body.filename}"

    # presigned URL 생성
    storage = StorageService()
    presigned_url = await storage.generate_presigned_put(storage_key, body.content_type)

    # DB에 pending 상태로 기록
    file_record = InspectionFile(
        id=uuid.uuid4(),
        inspection_id=inspection.id,
        tenant_id=user.tenant_id,
        original_filename=body.filename,
        storage_key=storage_key,
        file_type=file_type,
        mime_type=body.content_type,
        size_bytes=body.size_bytes,
        gps_lat=body.gps_lat,
        gps_lon=body.gps_lon,
        altitude_m=body.altitude_m,
        focal_length_mm=body.focal_length_mm,
        sensor_width_mm=body.sensor_width_mm,
        image_width_px=body.image_width_px,
    )
    db.add(file_record)
    inspection.status = InspectionStatus.uploading
    await db.commit()

    return FileUploadResponse(
        file_id=str(file_record.id),
        presigned_url=presigned_url,
        storage_key=storage_key,
    )


@router.post("/{inspection_id}/files/confirm", response_model=FileConfirmResponse)
async def confirm_upload(
    project_id: str,
    inspection_id: str,
    body: FileConfirmRequest,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    업로드 완료 신호 → 파일 카운트 업데이트 → Celery 분석 태스크 enqueue.
    이것이 '원클릭 분석 시작' 버튼의 백엔드 처리다.
    """
    inspection = await _get_inspection_or_404(inspection_id, project_id, user.tenant_id, db)

    # 파일 상태 업데이트
    file_ids = [uuid.UUID(fid) for fid in body.file_ids]
    result = await db.execute(
        select(InspectionFile).where(
            InspectionFile.id.in_(file_ids),
            InspectionFile.inspection_id == inspection.id,
        )
    )
    files = result.scalars().all()
    if not files:
        raise HTTPException(status_code=400, detail="확인할 파일이 없습니다")

    for f in files:
        f.upload_status = "uploaded" if hasattr(f, "upload_status") else None

    inspection.file_count = len(files)
    inspection.total_size_bytes = sum(f.size_bytes or 0 for f in files)
    inspection.status = InspectionStatus.queued

    await db.commit()

    # Celery 분석 태스크 enqueue
    job_id = await enqueue_analysis(str(inspection.id), str(user.tenant_id), db)

    return FileConfirmResponse(
        inspection_id=str(inspection.id),
        job_id=job_id,
        status="queued",
    )


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

async def _get_project_or_404(project_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.id == uuid.UUID(project_id),
            Project.tenant_id == tenant_id,
            Project.deleted_at.is_(None),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    return project


async def _get_inspection_or_404(
    inspection_id: str, project_id: str, tenant_id: uuid.UUID, db: AsyncSession
) -> Inspection:
    result = await db.execute(
        select(Inspection).where(
            Inspection.id == uuid.UUID(inspection_id),
            Inspection.project_id == uuid.UUID(project_id),
            Inspection.tenant_id == tenant_id,
            Inspection.deleted_at.is_(None),
        )
    )
    inspection = result.scalar_one_or_none()
    if not inspection:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")
    return inspection


def _to_response(i: Inspection) -> InspectionResponse:
    return InspectionResponse(
        id=str(i.id),
        project_id=str(i.project_id),
        tenant_id=str(i.tenant_id),
        label=i.label,
        drone_model=i.drone_model,
        flight_altitude_m=float(i.flight_altitude_m) if i.flight_altitude_m else None,
        inspection_date=i.inspection_date,
        status=i.status.value,
        file_count=i.file_count,
        total_size_bytes=i.total_size_bytes,
        created_at=i.created_at,
    )
