from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    address: str | None = None
    building_type: str | None = None
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    building_type: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    address: str | None
    building_type: str | None
    description: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
