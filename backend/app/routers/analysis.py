import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models.analysis import AnalysisJob, AnalysisResult, SeverityLevel
from app.models.user import User
from app.schemas.analysis import JobStatusResponse, AnalysisResultResponse, AnalysisResultListResponse, BoundingBox
from app.services.storage_service import StorageService

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """분석 진행 상태 + 진행률 조회. 프론트엔드가 3초마다 폴링."""
    job = await _get_job_or_404(job_id, user.tenant_id, db)
    return JobStatusResponse(
        id=str(job.id),
        inspection_id=str(job.inspection_id),
        status=job.status.value,
        progress_pct=job.progress_pct,
        model_version=job.model_version,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


@router.get("/jobs/{job_id}/results", response_model=AnalysisResultListResponse)
async def get_job_results(
    job_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    severity: str | None = Query(None, description="low|medium|high|critical 필터"),
):
    """분석 결과 목록. 어노테이션 이미지 presigned URL 포함."""
    job = await _get_job_or_404(job_id, user.tenant_id, db)

    query = select(AnalysisResult).where(
        AnalysisResult.job_id == job.id,
        AnalysisResult.tenant_id == user.tenant_id,
    )
    if severity:
        query = query.where(AnalysisResult.severity == SeverityLevel(severity))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(AnalysisResult.severity_score.desc()).offset(skip).limit(limit)
    )
    rows = result.scalars().all()

    # 심각도별 집계
    count_q = select(
        AnalysisResult.severity,
        func.count(AnalysisResult.id),
    ).where(
        AnalysisResult.job_id == job.id,
        AnalysisResult.tenant_id == user.tenant_id,
    ).group_by(AnalysisResult.severity)
    count_result = await db.execute(count_q)
    by_severity = {row[0].value: row[1] for row in count_result.all()}

    storage = StorageService()
    items = []
    for r in rows:
        img_url = None
        if r.annotated_image_key:
            img_url = await storage.generate_presigned_get(r.annotated_image_key)

        bbox_dict = r.bounding_box or {}
        items.append(AnalysisResultResponse(
            id=str(r.id),
            job_id=str(r.job_id),
            inspection_file_id=str(r.inspection_file_id),
            defect_type=r.defect_type.value,
            severity_score=r.severity_score,
            severity=r.severity.value,
            confidence=float(r.confidence),
            bounding_box=BoundingBox(
                x=bbox_dict.get("x", 0),
                y=bbox_dict.get("y", 0),
                w=bbox_dict.get("w", 0),
                h=bbox_dict.get("h", 0),
            ),
            crack_width_mm=float(r.crack_width_mm) if r.crack_width_mm else None,
            crack_length_mm=float(r.crack_length_mm) if r.crack_length_mm else None,
            crack_area_cm2=float(r.crack_area_cm2) if r.crack_area_cm2 else None,
            affected_area_pct=float(r.affected_area_pct) if r.affected_area_pct else None,
            annotated_image_url=img_url,
            created_at=r.created_at,
        ))

    return AnalysisResultListResponse(
        items=items,
        total=total or 0,
        summary={
            "total": total or 0,
            "by_severity": {
                "low": by_severity.get("low", 0),
                "medium": by_severity.get("medium", 0),
                "high": by_severity.get("high", 0),
                "critical": by_severity.get("critical", 0),
            },
        },
    )


async def _get_job_or_404(job_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> AnalysisJob:
    result = await db.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == uuid.UUID(job_id),
            AnalysisJob.tenant_id == tenant_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다")
    return job
