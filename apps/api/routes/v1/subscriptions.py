"""Mini-app surface for recurring subscriptions.

The mini-app cannot charge anyone. Telegram only bills a subscription through an invoice
link created with `subscription_period`, so `POST /subscriptions/checkout` returns a link
for the client to open and credits appear only once Telegram delivers the charge to the bot.
No endpoint here grants credits — one that did would be a way to get them for free.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.deps import (
    get_current_user,
    get_db_session,
    get_payment_gateway,
    get_settings_dep,
)
from kelbet.config import Settings
from kelbet.payments.gateway import SubscriptionGateway
from kelbet.services.auth import SessionUser
from kelbet.services.payment import payment_new_purchase_allowed, payment_support_url
from kelbet.services.subscription import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SubscriptionPlanResponse(BaseModel):
    slug: str
    plan_key: str
    name: str
    description: str
    credits_per_period: int
    stars: int
    price_kzt: int | None
    period_days: int
    referral_percent: int


class SubscriptionStateResponse(BaseModel):
    subscription_id: str
    plan_slug: str
    status: str
    current_period_start: str
    current_period_end: str
    current_period_index: int
    cancel_at_period_end: bool
    renewal_failed: bool


class SubscriptionPlansResponse(BaseModel):
    items: list[SubscriptionPlanResponse]
    subscriptions_enabled: bool
    current: SubscriptionStateResponse | None
    terms_url: str
    terms_version: str
    refund_policy_url: str
    support_url: str


class SubscriptionCheckoutRequest(BaseModel):
    plan_slug: str = Field(min_length=1, max_length=32)
    terms_accepted: bool
    terms_version: str | None = Field(default=None, min_length=1, max_length=32)


class SubscriptionCheckoutResponse(BaseModel):
    subscription_id: str
    plan_slug: str
    plan_name: str
    stars: int
    credits_per_period: int
    period_days: int
    invoice_url: str


class SubscriptionCancelResponse(BaseModel):
    subscription_id: str
    cancel_at_period_end: bool
    access_until: str


@router.get("/plans", response_model=SubscriptionPlansResponse)
async def list_subscription_plans(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> SubscriptionPlansResponse:
    service = SubscriptionService(session, settings)
    plans = await service.list_plans(current.language)
    state = await service.get_state(current.user_id)
    enabled = bool(
        settings.bot_token
        and settings.subscriptions_enabled
        and payment_new_purchase_allowed(settings, current.telegram_id)
    )
    return SubscriptionPlansResponse(
        items=[SubscriptionPlanResponse(**plan) for plan in plans],
        subscriptions_enabled=enabled,
        current=(
            None
            if state is None
            else SubscriptionStateResponse(
                subscription_id=str(state.subscription_id),
                plan_slug=state.plan_slug,
                status=state.status.value,
                current_period_start=state.current_period_start.isoformat(),
                current_period_end=state.current_period_end.isoformat(),
                current_period_index=state.current_period_index,
                cancel_at_period_end=state.cancel_at_period_end,
                renewal_failed=state.renewal_failed,
            )
        ),
        terms_url=settings.payment_terms_url,
        terms_version=settings.payment_terms_version,
        refund_policy_url=settings.payment_refund_policy_url,
        support_url=payment_support_url(settings),
    )


@router.post("/checkout", response_model=SubscriptionCheckoutResponse)
async def create_subscription_checkout(
    body: SubscriptionCheckoutRequest,
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    gateway: SubscriptionGateway = Depends(get_payment_gateway),
) -> SubscriptionCheckoutResponse:
    """Return a recurring invoice link. Idempotent per user without an explicit key.

    A retry cannot create a second subscription because a user has at most one row and a
    repeated checkout for the same plan reuses its payload, so no `Idempotency-Key` header
    is needed to stay safe.
    """
    checkout = await SubscriptionService(session, settings).start_checkout(
        current.user_id,
        body.plan_slug,
        language=current.language,
        terms_accepted=body.terms_accepted,
        accepted_terms_version=body.terms_version,
    )
    invoice_url = await gateway.create_subscription_link(checkout)
    return SubscriptionCheckoutResponse(
        subscription_id=str(checkout.subscription_id),
        plan_slug=checkout.plan_slug,
        plan_name=checkout.plan_name,
        stars=checkout.stars,
        credits_per_period=checkout.credits_per_period,
        period_days=checkout.subscription_period_seconds // 86_400,
        invoice_url=invoice_url,
    )


@router.post("/cancel", response_model=SubscriptionCancelResponse)
async def cancel_subscription(
    current: SessionUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
    gateway: SubscriptionGateway = Depends(get_payment_gateway),
) -> SubscriptionCancelResponse:
    """Stop renewal. Access continues to the end of the period already paid for."""
    result = await SubscriptionService(session, settings).request_cancel(current.user_id)
    if result.root_charge_id is not None:
        # Telegram is told after the local state is written, so a failure here leaves the
        # user with the cancellation they asked for instead of an error.
        await gateway.set_subscription_cancelled(
            user_id=result.telegram_id,
            charge_id=result.root_charge_id,
            cancelled=True,
        )
    return SubscriptionCancelResponse(
        subscription_id=str(result.subscription_id),
        cancel_at_period_end=True,
        access_until=result.access_until.isoformat(),
    )
