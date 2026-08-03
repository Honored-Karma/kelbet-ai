"""Bot surface for recurring Stars subscriptions.

Subscriptions share Telegram's payment updates with one-off credit packs, so every handler
here filters on the `kelbet-sub:` payload prefix and the pack handlers in `payments.py`
carry the matching negative filter. Both filters are explicit rather than relying on router
order: a reordering in `build_root_router` would otherwise route a paid subscription into
the one-off path, where it is rejected as an unknown order and the user gets nothing.
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

_PAYLOAD = f"{SUBSCRIPTION_PAYLOAD_PREFIX}:"
SUBSCRIPTION_PAYMENT_FILTER = F.successful_payment.invoice_payload.startswith(_PAYLOAD)
SUBSCRIPTION_PRE_CHECKOUT_FILTER = F.invoice_payload.startswith(_PAYLOAD)


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
    return value.strftime("%d.%m.%Y") if value is not None else "—"


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
    state = await service.get_state(registration.user.id)
    if state is not None and state.status != SubscriptionStatus.PENDING:
        name = await service.plan_name(registration.user.id, language)
        plans = await service.list_plans(language)
        credits = next(
            (plan["credits_per_period"] for plan in plans if plan["slug"] == state.plan_slug),
            0,
        )
        await message.answer(
            t(
                Msg.SUBSCRIPTION_ACTIVE,
                language,
                name=name,
                credits=credits,
                until=_until(state.current_period_end),
            ),
            reply_markup=_cancel_keyboard(language, settings),
        )
        return

    plans = await service.list_plans(language)
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
                        name=plan["name"],
                        credits=plan["credits_per_period"],
                        stars=plan["stars"],
                    ),
                    callback_data=f"sub_pick:{token}:{plan['slug']}",
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
    # A keyboard from before a terms change must not stay usable: the user would be
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
            registration.user.id,
            plan_slug,
            language=language,
            terms_accepted=True,
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
        # The pending row survives, so tapping again reuses the same payload rather than
        # leaving the user with two links that both bill.
        get_metrics().incr(
            "subscription.operation", tags={"operation": "link", "outcome": "failed"}
        )
        await callback.answer(t(Msg.SUBSCRIPTION_UNAVAILABLE, language), show_alert=True)
        return

    await callback.message.answer(
        t(
            Msg.SUBSCRIPTION_OPEN_PAYMENT,
            language,
            name=checkout.plan_name,
            credits=checkout.credits_per_period,
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
    if callback.from_user is None or callback.message is None:
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
        result = await SubscriptionService(session, settings).request_cancel(registration.user.id)
    except KelbetError:
        await callback.answer(t(Msg.SUBSCRIPTION_NONE, language), show_alert=True)
        return

    # Local state is already written. Telling Telegram can fail, and if it does the user
    # still sees the cancellation they asked for rather than an error; the remote side can
    # be retried. The reverse order could stop billing while our records claim it runs.
    if result.root_charge_id and callback.bot is not None:
        with suppress(StarsGatewayError):
            await AiogramStarsGateway(callback.bot).set_subscription_cancelled(
                user_id=result.telegram_id,
                charge_id=result.root_charge_id,
                cancelled=True,
            )
    await callback.message.answer(
        t(Msg.SUBSCRIPTION_CANCELLED, language, until=_until(result.access_until))
    )
    await callback.answer()


@router.pre_checkout_query(SUBSCRIPTION_PRE_CHECKOUT_FILTER)
async def on_pre_checkout(
    query: PreCheckoutQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Answer inside Telegram's window, or the payment is dropped.

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
        decision = await asyncio.wait_for(
            SubscriptionService(session, settings).validate_pre_checkout(
                telegram_id=query.from_user.id,
                invoice_payload=query.invoice_payload,
                currency=query.currency,
                total_amount=query.total_amount,
            ),
            timeout=6.5,
        )
        if decision.ok:
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


@router.message(SUBSCRIPTION_PAYMENT_FILTER)
async def on_successful_payment(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None or message.successful_payment is None:
        return
    language = await _language(session, message.from_user.id)
    payment = message.successful_payment
    outcome = await SubscriptionService(session, settings).apply_charge(
        telegram_id=message.from_user.id,
        invoice_payload=payment.invoice_payload,
        currency=payment.currency,
        total_amount=payment.total_amount,
        charge_id=payment.telegram_payment_charge_id,
        expires_at=_expiration(payment.subscription_expiration_date),
        language=language,
    )
    if outcome.error_code is not None or outcome.balance is None:
        await message.answer(t(Msg.SUBSCRIPTION_REVIEW, language))
        return
    # `is_first` comes from our own records, so the wording cannot disagree with what was
    # actually credited.
    key = Msg.SUBSCRIPTION_STARTED if outcome.is_first else Msg.SUBSCRIPTION_RENEWED
    await message.answer(
        t(
            key,
            language,
            name=outcome.plan_name,
            credits=outcome.credits,
            balance=outcome.balance,
            until=_until(outcome.period_end),
        )
    )


@router.subscription()
async def on_subscription_state(
    event: BotSubscriptionUpdated,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Handle a subscription state change Telegram reports on its own.

    This is how we learn the user cancelled from Telegram's UI, re-enabled, or that a
    renewal could not be collected. Without it a user could cancel in Telegram while our
    records kept claiming the subscription was renewing.
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
    registration = await RegistrationService(session).handle_start(
        event.user.id, event.user.username
    )
    if registration.user is None:
        return
    state = await service.get_state(registration.user.id)
    if state is None:
        return
    name = await service.plan_name(registration.user.id, language)
    with suppress(Exception):
        await event.bot.send_message(
            event.user.id,
            t(
                Msg.SUBSCRIPTION_RENEWAL_FAILED,
                language,
                name=name,
                until=_until(state.current_period_end),
            ),
        )
