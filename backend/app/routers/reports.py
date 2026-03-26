import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.report import Report, ReportStatus
from app.models.inspection import Inspection
from app.models.user import User
from app.services.storage_service import StorageService
from app.services.report_service import generate_report

router = APIRouter()


@router.post("/inspections/{inspection_id}/reports", status_code=202)
async def create_report(
    inspection_id: str,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """PDF 리포트 생성 요청. 백그라운드에서 생성 후 완료."""
    result = await db.execute(
        select(Inspection).where(
            Inspection.id == uuid.UUID(inspection_id),
            Inspection.tenant_id == user.tenant_id,
        )
    )
    inspection = result.scalar_one_or_none()
    if not inspection:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")

    report = Report(
        id=uuid.uuid4(),
        inspection_id=inspection.id,
        tenant_id=user.tenant_id,
        generated_by=user.id,
        status=ReportStatus.generating,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(report)
    await db.commit()

    # 백그라운드에서 PDF 생성
    background_tasks.add_task(_run_report_generation, str(report.id), inspection_id)

    return {"report_id": str(report.id), "status": "generating"}


@router.get("/reports/{report_id}")
async def get_report_status(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    report = await _get_report_or_404(report_id, user.tenant_id, db)
    return {
        "id": str(report.id),
        "status": report.status.value,
        "inspection_id": str(report.inspection_id),
        "version": report.version,
        "created_at": report.created_at,
    }


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """presigned GET URL로 리다이렉트 (1시간 유효)."""
    report = await _get_report_or_404(report_id, user.tenant_id, db)
    if report.status != ReportStatus.completed:
        raise HTTPException(status_code=400, detail=f"리포트 상태: {report.status.value}")
    if not report.storage_key:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    storage = StorageService()
    url = await storage.generate_presigned_get(report.storage_key, expires=3600)
    return RedirectResponse(url=url)


async def _get_report_or_404(report_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> Report:
    result = await db.execute(
        select(Report).where(
            Report.id == uuid.UUID(report_id),
            Report.tenant_id == tenant_id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    return report


async def _run_report_generation(report_id: str, inspection_id: str):
    """백그라운드 태스크: PDF 생성 후 DB 업데이트."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            storage_key = await generate_report(inspection_id, report_id, db)
            result = await db.execute(select(Report).where(Report.id == uuid.UUID(report_id)))
            report = result.scalar_one()
            report.storage_key = storage_key
            report.status = ReportStatus.completed
            await db.commit()
        except Exception as e:
            result = await db.execute(select(Report).where(Report.id == uuid.UUID(report_id)))
            report = result.scalar_one_or_none()
            if report:
                report.status = ReportStatus.failed
                await db.commit()
