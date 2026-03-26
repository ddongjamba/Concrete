"""
균열 시계열 추적 API

GET /projects/{project_id}/defect-tracks        — 건물의 균열 목록 (status 필터)
GET /defect-tracks/{track_id}                   — 단일 균열 시계열 데이터 (차트용)
GET /defect-tracks/{track_id}/compare           — 두 점검 비교 (?a=inspId&b=inspId)
PATCH /defect-tracks/{track_id}                 — status 수동 변경 (오탐지 처리 / 수리 완료 등)
"""
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.defect_track import DefectTrack, DefectTrackEntry, TrackStatus
from app.models.user import User
from app.services.storage_service import StorageService

router = APIRouter()


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

class EntryOut(BaseModel):
    id: str
    inspection_id: str
    inspection_date: Optional[str]
    severity_score: int
    crack_width_mm: Optional[float]
    crack_length_mm: Optional[float]
    crack_area_cm2: Optional[float]
    change_vs_prev: Optional[dict]
    annotated_image_url: Optional[str]

    model_config = {"from_attributes": True}


class TrackSummary(BaseModel):
    id: str
    project_id: str
    first_seen_at: Optional[str]
    location_zone: Optional[str]
    status: str
    latest_severity_score: Optional[int]
    latest_crack_width_mm: Optional[float]
    entry_count: int
    representative_image_url: Optional[str]


class TrackDetail(BaseModel):
    id: str
    project_id: str
    first_seen_at: Optional[str]
    location_zone: Optional[str]
    status: str
    entries: list[EntryOut]


class TrackPatch(BaseModel):
    status: TrackStatus
    location_zone: Optional[str] = None


class CompareEntry(BaseModel):
    inspection_id: str
    inspection_date: Optional[str]
    severity_score: int
    crack_width_mm: Optional[float]
    crack_length_mm: Optional[float]
    crack_area_cm2: Optional[float]
    annotated_image_url: Optional[str]
    change_vs_prev: Optional[dict]


class CompareResponse(BaseModel):
    track_id: str
    a: Optional[CompareEntry]
    b: Optional[CompareEntry]


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

async def _get_track_or_404(track_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> DefectTrack:
    result = await db.execute(
        select(DefectTrack).where(
            DefectTrack.id == uuid.UUID(track_id),
            DefectTrack.tenant_id == tenant_id,
        )
    )
    track = result.scalar_one_or_none()
    if not track:
        raise HTTPException(status_code=404, detail="균열 트랙을 찾을 수 없습니다")
    return track


def _entry_to_out(entry: DefectTrackEntry, storage: StorageService) -> EntryOut:
    return EntryOut(
        id=str(entry.id),
        inspection_id=str(entry.inspection_id),
        inspection_date=str(entry.inspection_date) if entry.inspection_date else None,
        severity_score=entry.severity_score,
        crack_width_mm=float(entry.crack_width_mm) if entry.crack_width_mm else None,
        crack_length_mm=float(entry.crack_length_mm) if entry.crack_length_mm else None,
        crack_area_cm2=float(entry.crack_area_cm2) if entry.crack_area_cm2 else None,
        change_vs_prev=entry.change_vs_prev,
        annotated_image_url=(
            storage.generate_presigned_get(entry.annotated_image_key)
            if entry.annotated_image_key else None
        ),
    )


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/defect-tracks", response_model=list[TrackSummary])
async def list_defect_tracks(
    project_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[str] = Query(None, description="monitoring|worsening|stable|repaired|needs_review"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """건물의 모든 균열 트랙 목록. 최신 엔트리 수치 포함."""
    storage = StorageService()

    q = select(DefectTrack).where(
        DefectTrack.project_id == uuid.UUID(project_id),
        DefectTrack.tenant_id == user.tenant_id,
    )
    if status:
        try:
            q = q.where(DefectTrack.status == TrackStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"유효하지 않은 status: {status}")

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    tracks = result.scalars().all()

    out = []
    for track in tracks:
        # 최신 엔트리
        latest_result = await db.execute(
            select(DefectTrackEntry)
            .where(DefectTrackEntry.track_id == track.id)
            .order_by(DefectTrackEntry.inspection_date.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()

        entry_count_result = await db.execute(
            select(DefectTrackEntry.id).where(DefectTrackEntry.track_id == track.id)
        )
        entry_count = len(entry_count_result.all())

        out.append(TrackSummary(
            id=str(track.id),
            project_id=str(track.project_id),
            first_seen_at=str(track.first_seen_at) if track.first_seen_at else None,
            location_zone=track.location_zone,
            status=track.status.value,
            latest_severity_score=latest.severity_score if latest else None,
            latest_crack_width_mm=float(latest.crack_width_mm) if (latest and latest.crack_width_mm) else None,
            entry_count=entry_count,
            representative_image_url=(
                storage.generate_presigned_get(track.representative_image_key)
                if track.representative_image_key else None
            ),
        ))
    return out


@router.get("/defect-tracks/{track_id}", response_model=TrackDetail)
async def get_defect_track(
    track_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """단일 균열의 전체 시계열 데이터. 프론트엔드 트렌드 차트용."""
    storage = StorageService()
    track = await _get_track_or_404(track_id, user.tenant_id, db)

    entries_result = await db.execute(
        select(DefectTrackEntry)
        .where(DefectTrackEntry.track_id == track.id)
        .order_by(DefectTrackEntry.inspection_date.asc())
    )
    entries = entries_result.scalars().all()

    return TrackDetail(
        id=str(track.id),
        project_id=str(track.project_id),
        first_seen_at=str(track.first_seen_at) if track.first_seen_at else None,
        location_zone=track.location_zone,
        status=track.status.value,
        entries=[_entry_to_out(e, storage) for e in entries],
    )


@router.get("/defect-tracks/{track_id}/compare", response_model=CompareResponse)
async def compare_entries(
    track_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    a: str = Query(..., description="비교 기준 점검 ID"),
    b: str = Query(..., description="비교 대상 점검 ID"),
):
    """두 점검의 동일 균열 나란히 비교."""
    storage = StorageService()
    track = await _get_track_or_404(track_id, user.tenant_id, db)

    async def _fetch(insp_id: str) -> Optional[CompareEntry]:
        result = await db.execute(
            select(DefectTrackEntry).where(
                DefectTrackEntry.track_id == track.id,
                DefectTrackEntry.inspection_id == uuid.UUID(insp_id),
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None
        return CompareEntry(
            inspection_id=insp_id,
            inspection_date=str(entry.inspection_date) if entry.inspection_date else None,
            severity_score=entry.severity_score,
            crack_width_mm=float(entry.crack_width_mm) if entry.crack_width_mm else None,
            crack_length_mm=float(entry.crack_length_mm) if entry.crack_length_mm else None,
            crack_area_cm2=float(entry.crack_area_cm2) if entry.crack_area_cm2 else None,
            annotated_image_url=(
                storage.generate_presigned_get(entry.annotated_image_key)
                if entry.annotated_image_key else None
            ),
            change_vs_prev=entry.change_vs_prev,
        )

    return CompareResponse(
        track_id=track_id,
        a=await _fetch(a),
        b=await _fetch(b),
    )


@router.patch("/defect-tracks/{track_id}")
async def update_track(
    track_id: str,
    body: TrackPatch,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """status 수동 변경 (예: 수리 완료 → 'repaired', 오탐지 → 수동 연결 해제)."""
    track = await _get_track_or_404(track_id, user.tenant_id, db)
    track.status = body.status
    if body.location_zone is not None:
        track.location_zone = body.location_zone
    await db.commit()
    return {"id": track_id, "status": track.status.value}
