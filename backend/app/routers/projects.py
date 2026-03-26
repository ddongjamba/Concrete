import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse

router = APIRouter()


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    base_q = (
        select(Project)
        .where(Project.tenant_id == user.tenant_id, Project.deleted_at.is_(None))
    )
    total = await db.scalar(select(func.count()).select_from(base_q.subquery()))
    result = await db.execute(base_q.order_by(Project.created_at.desc()).offset(skip).limit(limit))
    projects = result.scalars().all()

    return ProjectListResponse(
        items=[_to_response(p) for p in projects],
        total=total or 0,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = Project(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        created_by=user.id,
        **body.model_dump(),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await _get_or_404(project_id, user.tenant_id, db)
    return _to_response(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: Annotated[User, Depends(require_role("admin", "manager"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await _get_or_404(project_id, user.tenant_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await _get_or_404(project_id, user.tenant_id, db)
    project.deleted_at = datetime.now(timezone.utc)
    await db.commit()


async def _get_or_404(project_id: str, tenant_id: uuid.UUID, db: AsyncSession) -> Project:
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


def _to_response(p: Project) -> ProjectResponse:
    return ProjectResponse(
        id=str(p.id),
        tenant_id=str(p.tenant_id),
        name=p.name,
        address=p.address,
        building_type=p.building_type,
        description=p.description,
        status=p.status.value,
        created_at=p.created_at,
    )
