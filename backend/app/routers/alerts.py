"""
앱 내 알림 API

GET  /alerts              — 읽지 않은 알림 목록
POST /alerts/{id}/read    — 읽음 처리
POST /alerts/read-all     — 전체 읽음 처리
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert import DefectAlert
from app.models.user import User

router = APIRouter()


class AlertOut(BaseModel):
    id: str
    track_id: str
    alert_type: str
    title: str
    body: str | None
    is_read: bool
    created_at: str


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    q = select(DefectAlert).where(DefectAlert.tenant_id == user.tenant_id)
    if unread_only:
        q = q.where(DefectAlert.is_read == False)  # noqa: E712
    q = q.order_by(DefectAlert.created_at.desc()).limit(limit)
    result = await db.execute(q)
    alerts = result.scalars().all()
    return [AlertOut(
        id=str(a.id),
        track_id=str(a.track_id),
        alert_type=a.alert_type,
        title=a.title,
        body=a.body,
        is_read=a.is_read,
        created_at=str(a.created_at),
    ) for a in alerts]


@router.post("/alerts/{alert_id}/read")
async def mark_read(
    alert_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(
        update(DefectAlert)
        .where(DefectAlert.id == uuid.UUID(alert_id), DefectAlert.tenant_id == user.tenant_id)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}


@router.post("/alerts/read-all")
async def mark_all_read(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await db.execute(
        update(DefectAlert)
        .where(DefectAlert.tenant_id == user.tenant_id, DefectAlert.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}
