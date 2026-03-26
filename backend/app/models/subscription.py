import uuid
from sqlalchemy import String, Enum, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import mapped_column, Mapped
from app.models.base import UUIDBase
from datetime import datetime
import enum


class SubscriptionPlan(str, enum.Enum):
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    unpaid = "unpaid"


class Subscription(UUIDBase):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), unique=True, nullable=False)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(100))
    plan: Mapped[SubscriptionPlan] = mapped_column(Enum(SubscriptionPlan))
    status: Mapped[SubscriptionStatus] = mapped_column(Enum(SubscriptionStatus))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
