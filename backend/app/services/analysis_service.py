"""
분석 태스크 관리 서비스.
Celery 태스크를 enqueue하고 analysis_jobs 레코드를 생성한다.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisJob, JobStatus
from app.models.inspection import Inspection, InspectionStatus
from app.config import settings


async def enqueue_analysis(
    inspection_id: str,
    tenant_id: str,
    db: AsyncSession,
    model_version: str = "yolov8n-crack-v1",
) -> str:
    """
    분석 Celery 태스크를 enqueue하고 job_id를 반환한다.
    실제 Celery 연결은 워커 서비스에서 처리한다.
    """
    from celery import Celery
    from app.core.celery_app import celery_app

    job = AnalysisJob(
        id=uuid.uuid4(),
        inspection_id=uuid.UUID(inspection_id),
        tenant_id=uuid.UUID(tenant_id),
        model_version=model_version,
        status=JobStatus.queued,
        progress_pct=0,
    )
    db.add(job)

    # Inspection 상태 업데이트
    from sqlalchemy import select
    result = await db.execute(
        select(Inspection).where(Inspection.id == uuid.UUID(inspection_id))
    )
    inspection = result.scalar_one_or_none()
    if inspection:
        inspection.status = InspectionStatus.queued

    await db.flush()

    # Celery 태스크 enqueue
    task = celery_app.send_task(
        "tasks.analysis_tasks.run_inspection_analysis",
        args=[inspection_id, str(job.id)],
        queue="analysis",
    )
    job.celery_task_id = task.id

    await db.commit()
    return str(job.id)
