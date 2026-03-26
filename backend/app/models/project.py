import uuid
from sqlalchemy import String, Text, Enum, ForeignKey, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase
from datetime import datetime
import enum


class ProjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class Project(UUIDBase):
    __tablename__ = "projects"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    building_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.active)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped["Tenant"] = relationship(back_populates="projects")
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="project")
    defect_tracks: Mapped[list["DefectTrack"]] = relationship(back_populates="project")
