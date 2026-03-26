import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.database import get_db
from app.dependencies import get_current_user
from app.models.tenant import Tenant, PlanType
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserMe

router = APIRouter()


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:100]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    """테넌트 + 어드민 유저를 한 번에 생성"""
    # 이메일 중복 확인 (전체 tenant에 걸쳐)
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    # slug 생성 및 중복 처리
    base_slug = _slugify(body.tenant_name)
    slug = base_slug
    suffix = 1
    while True:
        exists = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if not exists.scalar_one_or_none():
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    tenant = Tenant(
        id=uuid.uuid4(),
        name=body.tenant_name,
        slug=slug,
        plan=PlanType.trial,
    )
    db.add(tenant)
    await db.flush()  # tenant.id 확보

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=UserRole.admin,
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id), str(tenant.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")

    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.tenant_id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError
        user_id = payload["sub"]
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="유효하지 않은 refresh token입니다")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다")

    return TokenResponse(
        access_token=create_access_token(str(user.id), str(user.tenant_id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserMe)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return UserMe(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        email=user.email,
        role=user.role.value,
        full_name=user.full_name,
    )
