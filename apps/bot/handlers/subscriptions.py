"""Bot surface for recurring Stars subscriptions.

Subscription payments share Telegram's payment updates with one-off packs, so every
handler here is filtered on the `kelbet-sub:` payload prefix and the pack handlers in
`payments.py` carry the matching negative filter. Both filters are explicit rather than
relying on router order, because a reordering in `build_root_router` would otherwise send
subscription charges into the one-off path — where they would be rejected as unknown
orders and a paid user would get nothing.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BotSubscriptionUpdated,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings
from kelbet.domain.enums import Language, SubscriptionStatus
from kelbet.domain.exceptions import KelbetError
from kelbet.i18n import Msg, t
from kelbet.observability import get_metrics
from kelbet.payments.gateway import AiogramStarsGateway, StarsGatewayError
from kelbet.services.payment import payment_new_purchase_allowed
from kelbet.services.profile import ProfileService
from kelbet.services.registration import RegistrationService
from kelbet.services.subscription import (
    SUBSCRIPTION_PAYLOAD_PREFIX,
    SubscriptionService,
)

router = Router(name="subscriptions")

SUBSCRIPTION_PAYLOAD_FILTER = F.successful_payment.invoice_payload.startswith(
    f"{SUBSCRIPTION_PAYLOAD_PREFIX}:"
)
PRE_CHECKOUT_PAYLOAD_FILTER = F.invoice_payload.startswith(f"{SUBSCRIPTION_PAYLOAD_PREFIX}:")


def _ready(settings: Settings, telegram_id: int) -> bool:
    return bool(
        settings.bot_token
        and settings.subscriptions_enabled
        and payment_new_purchase_allowed(settings, telegram_id)
    )


def _terms_token(settings: Settings) -> str:
    return sha256(settings.payment_terms_version.encode("utf-8")).hexdigest()[:12]


async def _language(session: AsyncSession, telegram_id: int) -> Language:
    try:
        return (await ProfileService(session).get_profile(telegram_id)).language
    except KelbetError:
        return Language.KK


def _expiration(value: int | None) -> datetime | None:
    """Telegram reports `subscription_expiration_date` as Unix seconds, not a datetime.

    Converting at the boundary keeps the service free of Telegram's wire format, and
    anchoring to UTC keeps the stored deadline independent of the host's timezone.
    """
    return None if value is None else datetime.fromtimestamp(value, tz=UTC)


def _until(value: datetime | None) -> str:
    """Render a renewal date. Subscriptions always have one once charged; a dash covers the
    window between checkout and the first charge, where Telegram has not set a date yet."""
    return value.strftime("%d.%m.%Y") if value is not None else "—"


@router.message(Command("subscribe"))
async def on_subscribe(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    registration = await RegistrationService(session).handle_start(
        message.from_user.id,
        message.from_user.username,
    )
    if registration.user is None:
        await message.answer(t(Msg.NEED_REGISTER, Language.KK))
        return
    language = registration.user.language
    if not _ready(settings, message.from_user.id):
        await message.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language))
        return

    service = SubscriptionService(session, settings)
    state = await service.get_state(registration.user.id, language)
    if state is not None and state.status != SubscriptionStatus.PENDING:
        await message.answer(
            t(
                Msg.SUBSCRIPTION_ACTIVE,
                language,
                name=state.plan_name,
                credits=state.monthly_credits,
                until=_until(state.current_period_end),
            ),
            reply_markup=_cancel_keyboard(language, settings),
        )
        return

    plans = await service.list_plans(language, telegram_id=message.from_user.id)
    if not plans:
        await message.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language))
        return
    token = _terms_token(settings)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(
                        Msg.SUBSCRIPTION_PLAN_BUTTON,
                        language,
                        name=plan.name,
                        credits=plan.monthly_credits,
                        stars=plan.stars,
                    ),
                    callback_data=f"sub_pick:{token}:{plan.slug}",
                )
            ]
            for plan in plans
        ]
        + [
            [
                InlineKeyboardButton(
                    text=t(Msg.PAYMENT_TERMS_OPEN, language),
                    url=settings.payment_terms_url,
                )
            ]
        ]
    )
    await message.answer(t(Msg.SUBSCRIPTION_CHOOSE, language), reply_markup=keyboard)


def _cancel_keyboard(language: Language, settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(Msg.SUBSCRIPTION_CANCEL_BUTTON, language),
                    callback_data=f"sub_cancel:{_terms_token(settings)}",
                )
            ]
        ]
    )


@router.callback_query(F.data.startswith("sub_pick:"))
async def on_plan_pick(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return
    language = await _language(session, callback.from_user.id)
    if not _ready(settings, callback.from_user.id):
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return
    try:
        token, plan_slug = callback.data.removeprefix("sub_pick:").split(":", 1)
    except ValueError:
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return
    # A stale keyboard from before a terms change must not be usable: the user would be
    # agreeing to terms they never saw.
    if token != _terms_token(settings):
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return

    registration = await RegistrationService(session).handle_start(
        callback.from_user.id,
        callback.from_user.username,
    )
    if registration.user is None:
        await callback.answer(t(Msg.NEED_REGISTER, language), show_alert=True)
        return
    try:
        checkout = await SubscriptionService(session, settings).start_checkout(
            user_id=registration.user.id,
            plan_slug=plan_slug,
            idempotency_key=f"bot-sub:{callback.id}",
            terms_accepted=True,
            language=language,
            accepted_terms_version=settings.payment_terms_version,
        )
    except KelbetError:
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return

    if callback.bot is None:
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return
    try:
        link = await AiogramStarsGateway(callback.bot).create_subscription_link(checkout)
    except StarsGatewayError:
        # The pending row stays; the user can tap again and reuse the same payload.
        get_metrics().incr("subscription.event", tags={"event": "link", "outcome": "failed"})
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return

    await callback.message.answer(
        t(
            Msg.SUBSCRIPTION_OPEN_PAYMENT,
            language,
            name=checkout.plan_name,
            credits=checkout.monthly_credits,
            stars=checkout.stars,
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t(Msg.SUBSCRIPTION_PAY_BUTTON, language, stars=checkout.stars),
                        url=link,
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_cancel:"))
async def on_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return
    language = await _language(session, callback.from_user.id)
    registration = await RegistrationService(session).handle_start(
        callback.from_user.id,
        callback.from_user.username,
    )
    if registration.user is None:
        await callback.answer(t(Msg.NEED_REGISTER, language), show_alert=True)
        return
    try:
        result = await SubscriptionService(session, settings).request_cancel(
            user_id=registration.user.id
        )
    except KelbetError:
        await callback.answer(t(Msg.SUBSCRIPTION_NONE, language), show_alert=True)
        return

    # Local state is already committed by the caller's transaction. Telling Telegram can
    # fail, and if it does the user still sees the cancellation they asked for rather than
    # a confusing error; the next reconciliation pass can retry the remote side.
    if result.root_charge_id and callback.bot is not None:
        with suppress(StarsGatewayError):
            await AiogramStarsGateway(callback.bot).set_subscription_cancelled(
                user_id=result.telegram_id,
                charge_id=result.root_charge_id,
                cancelled=True,
            )
    await callback.message.answer(
        t(Msg.SUBSCRIPTION_CANCELLED, language, until=_until(result.current_period_end))
    )
    await callback.answer()


@router.pre_checkout_query(PRE_CHECKOUT_PAYLOAD_FILTER)
async def on_pre_checkout(
    query: PreCheckoutQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Answer within Telegram's 10-second window or the payment is dropped.

    Same timeout discipline as the one-off path: a slow database must produce an explicit
    rejection rather than silence, because silence charges nobody and explains nothing.
    """
    started = monotonic()
    outcome = "error"
    language = (
        Language.RU
        if (query.from_user.language_code or "").lower().startswith("ru")
        else Language.KK
    )
    try:
        result = await asyncio.wait_for(
            SubscriptionService(session, settings).validate_pre_checkout(
                telegram_id=query.from_user.id,
                invoice_payload=query.invoice_payload,
                currency=query.currency,
                total_amount=query.total_amount,
            ),
            timeout=6.5,
        )
        if result.ok:
            await asyncio.wait_for(query.answer(ok=True), timeout=1.25)
            outcome = "approved"
        else:
            await asyncio.wait_for(
                query.answer(ok=False, error_message=t(Msg.PAYMENT_CHECKOUT_REJECTED, language)),
                timeout=1.25,
            )
            outcome = "rejected"
    except TimeoutError:
        outcome = "timeout"
        with suppress(Exception):
            await asyncio.wait_for(
                query.answer(ok=False, error_message=t(Msg.PAYMENT_CHECKOUT_REJECTED, language)),
                timeout=1.0,
            )
    finally:
        get_metrics().observe(
            "subscription.pre_checkout_duration_seconds",
            monotonic() - started,
            tags={"outcome": outcome},
        )


@router.message(SUBSCRIPTION_PAYLOAD_FILTER)
async def on_successful_payment(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None or message.successful_payment is None:
        return
    language = await _language(session, message.from_user.id)
    payment = message.successful_payment
    result = await SubscriptionService(session, settings).apply_successful_payment(
        telegram_id=message.from_user.id,
        invoice_payload=payment.invoice_payload,
        currency=payment.currency,
        total_amount=payment.total_amount,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
        subscription_expiration_date=_expiration(payment.subscription_expiration_date),
        is_first_recurring=bool(payment.is_first_recurring),
    )
    if result.error_code is not None or result.balance is None:
        await message.answer(t(Msg.SUBSCRIPTION_REVIEW, language))
        return

    state = None
    if result.subscription_id is not None:
        state = await SubscriptionService(session, settings).get_state(
            (
                await RegistrationService(session).handle_start(
                    message.from_user.id, message.from_user.username
                )
            ).user.id,  # type: ignore[union-attr]
            language,
        )
    name = state.plan_name if state is not None else ""
    # `is_first_recurring` is only used for the wording here. Whether credits were granted
    # is decided in the service against our own records, never against this flag.
    key = Msg.SUBSCRIPTION_STARTED if payment.is_first_recurring else Msg.SUBSCRIPTION_RENEWED
    await message.answer(
        t(
            key,
            language,
            name=name,
            credits=result.credits,
            balance=result.balance,
            until=_until(result.period_end),
        )
    )


@router.subscription()
async def on_subscription_state(
    event: BotSubscriptionUpdated,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Handle a subscription state change Telegram reports on its own.

    This is how we learn that the user cancelled from Telegram's UI, re-enabled, or that a
    renewal could not be collected. Without it a user could cancel in Telegram and our
    records would keep claiming the subscription was renewing.
    """
    service = SubscriptionService(session, settings)
    if not await service.apply_telegram_state(
        invoice_payload=event.invoice_payload,
        state=event.state,
    ):
        return
    if event.state != "failed" or event.bot is None:
        return
    language = await _language(session, event.user.id)
    state = None
    user = (
        await RegistrationService(session).handle_start(event.user.id, event.user.username)
    ).user
    if user is not None:
        state = await service.get_state(user.id, language)
    if state is None:
        return
    with suppress(Exception):
        await event.bot.send_message(
            event.user.id,
            t(
                Msg.SUBSCRIPTION_RENEWAL_FAILED,
                language,
                name=state.plan_name,
                until=_until(state.current_period_end),
            ),
        )
