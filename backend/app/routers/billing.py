"""
Stripe 결제 라우터.

플로우:
1. POST /billing/checkout → Stripe Checkout 세션 생성 → 결제 페이지 URL 반환
2. 결제 완료 → Stripe가 /webhooks/stripe 호출
3. webhook: subscription 상태 DB 반영
4. POST /billing/portal → Stripe Customer Portal (구독 관리/취소)
"""
import hashlib
import hmac
import uuid
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter()

stripe.api_key = settings.stripe_secret_key

# 플랜별 Stripe Price ID (환경변수로 관리 권장)
PLAN_PRICES = {
    "starter": "price_starter_monthly",   # 실제 Stripe Dashboard에서 생성한 price ID로 교체
    "pro": "price_pro_monthly",
    "enterprise": "price_enterprise_monthly",
}


@router.post("/checkout")
async def create_checkout(
    plan: str,
    user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stripe Checkout 세션 생성. 반환된 URL로 프론트엔드를 리다이렉트."""
    if plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 플랜: {plan}")

    # 테넌트의 Stripe customer 생성 또는 조회
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one()

    customer_id = tenant.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=tenant.name,
            metadata={"tenant_id": str(tenant.id)},
        )
        customer_id = customer.id
        tenant.stripe_customer_id = customer_id
        await db.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": PLAN_PRICES[plan], "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.backend_cors_origins[0]}/settings/billing?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.backend_cors_origins[0]}/settings/billing",
        metadata={"tenant_id": str(tenant.id), "plan": plan},
    )
    return {"checkout_url": session.url}


@router.post("/portal")
async def create_portal(
    user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stripe Customer Portal (구독 변경/취소)."""
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one()

    if not tenant.stripe_customer_id:
        raise HTTPException(status_code=400, detail="결제 정보가 없습니다")

    session = stripe.billing_portal.Session.create(
        customer=tenant.stripe_customer_id,
        return_url=f"{settings.backend_cors_origins[0]}/settings/billing",
    )
    return {"portal_url": session.url}


@router.get("/subscription")
async def get_subscription(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """현재 구독 상태 조회."""
    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == user.tenant_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"plan": "trial", "status": "trialing"}
    return {
        "plan": sub.plan.value,
        "status": sub.status.value,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Stripe 웹훅 수신. HMAC 서명 검증 후 구독 이벤트 처리.
    인증 없음 (Stripe → 서버 직접 호출).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="웹훅 서명 검증 실패")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        await _upsert_subscription(data, db)
    elif event_type == "customer.subscription.deleted":
        await _cancel_subscription(data, db)

    return {"received": True}


async def _upsert_subscription(sub_data: dict, db: AsyncSession):
    # Stripe customer → tenant 매핑
    customer_result = await db.execute(
        select(Tenant).where(Tenant.stripe_customer_id == sub_data["customer"])
    )
    tenant = customer_result.scalar_one_or_none()
    if not tenant:
        return

    plan = sub_data.get("metadata", {}).get("plan", "starter")

    result = await db.execute(
        select(Subscription).where(Subscription.tenant_id == tenant.id)
    )
    sub = result.scalar_one_or_none()

    status_map = {
        "trialing": SubscriptionStatus.trialing,
        "active": SubscriptionStatus.active,
        "past_due": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "unpaid": SubscriptionStatus.unpaid,
    }

    if sub is None:
        sub = Subscription(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            stripe_subscription_id=sub_data["id"],
            plan=SubscriptionPlan(plan),
            status=status_map.get(sub_data["status"], SubscriptionStatus.active),
        )
        db.add(sub)
    else:
        sub.status = status_map.get(sub_data["status"], SubscriptionStatus.active)
        sub.stripe_subscription_id = sub_data["id"]

    from datetime import datetime, timezone
    sub.current_period_start = datetime.fromtimestamp(
        sub_data["current_period_start"], tz=timezone.utc
    )
    sub.current_period_end = datetime.fromtimestamp(
        sub_data["current_period_end"], tz=timezone.utc
    )
    sub.cancel_at_period_end = sub_data.get("cancel_at_period_end", False)

    # 테넌트 플랜 업데이트
    from app.models.tenant import PlanType
    try:
        tenant.plan = PlanType(plan)
    except ValueError:
        pass

    await db.commit()


async def _cancel_subscription(sub_data: dict, db: AsyncSession):
    result = await db.execute(
        select(Subscription).where(
            Subscription.stripe_subscription_id == sub_data["id"]
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = SubscriptionStatus.canceled
        await db.commit()
