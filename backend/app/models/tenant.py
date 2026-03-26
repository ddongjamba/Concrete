import uuid
from sqlalchemy import String, Boolean, Enum, Numeric
from sqlalchemy.orm import mapped_column, Mapped, relationship
from app.models.base import UUIDBase
import enum


class PlanType(str, enum.Enum):
    trial = "trial"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class Tenant(UUIDBase):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[PlanType] = mapped_column(Enum(PlanType), default=PlanType.trial)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_projects: Mapped[int] = mapped_column(default=5)
    max_storage_gb: Mapped[float] = mapped_column(Numeric(10, 2), default=5.0)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    projects: Mapped[list["Project"]] = relationship(back_populates="tenant")
