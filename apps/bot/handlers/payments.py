from __future__ import annotations

import asyncio
from contextlib import suppress
from hashlib import sha256
from time import monotonic

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from kelbet.config import Settings
from kelbet.domain.enums import Language
from kelbet.domain.exceptions import KelbetError
from kelbet.i18n import Msg, t
from kelbet.observability import get_metrics
from kelbet.services.payment import PaymentService, payment_new_purchase_allowed
from kelbet.services.profile import ProfileService
from kelbet.services.registration import RegistrationService

router = Router(name="payments")


def _payments_ready(settings: Settings, telegram_id: int) -> bool:
    return bool(settings.bot_token and payment_new_purchase_allowed(settings, telegram_id))


def _terms_token(settings: Settings) -> str:
    return sha256(settings.payment_terms_version.encode("utf-8")).hexdigest()[:12]


def _telegram_language(language_code: str | None) -> Language:
    return Language.RU if (language_code or "").lower().startswith("ru") else Language.KK


async def _language(session: AsyncSession, telegram_id: int) -> Language:
    try:
        return (await ProfileService(session).get_profile(telegram_id)).language
    except KelbetError:
        return Language.KK


@router.message(Command("buy"))
async def on_buy(
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
    if not _payments_ready(settings, message.from_user.id):
        await message.answer(t(Msg.PAYMENT_UNAVAILABLE, language))
        return
    buttons = [
        [
            InlineKeyboardButton(
                text=t(Msg.PAYMENT_TERMS_OPEN, language),
                url=settings.payment_terms_url,
            )
        ],
        [
            InlineKeyboardButton(
                text=t(Msg.PAYMENT_TERMS_ACCEPT, language),
                callback_data=f"pay_terms_accept:{_terms_token(settings)}",
            )
        ],
    ]
    await message.answer(
        t(Msg.PAYMENT_CHOOSE, language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("pay_terms_accept:"))
async def on_terms_accept(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return
    language = await _language(session, callback.from_user.id)
    if (
        not _payments_ready(settings, callback.from_user.id)
        or callback.data.removeprefix("pay_terms_accept:") != _terms_token(settings)
    ):
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    products = await PaymentService(session, settings).list_products(
        language, telegram_id=callback.from_user.id
    )
    token = _terms_token(settings)
    buttons = [
        [
            InlineKeyboardButton(
                text=t(
                    Msg.PAYMENT_PRODUCT_BUTTON,
                    language,
                    name=product.name,
                    credits=product.credits,
                    stars=product.stars,
                ),
                callback_data=f"pay_confirm:{token}:{product.slug}",
            )
        ]
        for product in products
    ]
    await callback.message.answer(
        t(Msg.PAYMENT_TERMS_ACCEPTED, language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_confirm:"))
async def on_payment_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return
    language = await _language(session, callback.from_user.id)
    if not _payments_ready(settings, callback.from_user.id):
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    try:
        token, product_slug = callback.data.removeprefix("pay_confirm:").split(":", 1)
    except ValueError:
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    if token != _terms_token(settings):
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    registration = await RegistrationService(session).handle_start(
        callback.from_user.id,
        callback.from_user.username,
    )
    if registration.user is None:
        await callback.answer(t(Msg.NEED_REGISTER, language), show_alert=True)
        return
    try:
        order = await PaymentService(session, settings).create_order(
            user_id=registration.user.id,
            product_slug=product_slug,
            idempotency_key=f"bot:{callback.id}",
            terms_accepted=True,
            language=language,
            accepted_terms_version=settings.payment_terms_version,
        )
    except KelbetError:
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    await callback.message.answer_invoice(
        title=order.product_name[:32],
        description=order.product_description[:255],
        payload=order.invoice_payload,
        currency=order.currency,
        prices=[
            LabeledPrice(
                label=t(Msg.PAYMENT_CREDITS_LABEL, language, credits=order.credits),
                amount=order.total_amount,
            )
        ],
        start_parameter=f"pay_{order.id.hex}",
    )
    await callback.answer()


@router.pre_checkout_query()
async def on_pre_checkout(
    query: PreCheckoutQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    started = monotonic()
    outcome = "error"
    language = _telegram_language(query.from_user.language_code)
    try:
        result = await asyncio.wait_for(
            PaymentService(session, settings).validate_pre_checkout(
                telegram_id=query.from_user.id,
                query_id=query.id,
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
                query.answer(
                    ok=False,
                    error_message=t(Msg.PAYMENT_CHECKOUT_REJECTED, language),
                ),
                timeout=1.25,
            )
            outcome = "rejected"
    except TimeoutError:
        outcome = "timeout"
        with suppress(Exception):
            await asyncio.wait_for(
                query.answer(
                    ok=False,
                    error_message=t(Msg.PAYMENT_CHECKOUT_REJECTED, language),
                ),
                timeout=1.0,
            )
    finally:
        get_metrics().observe(
            "payment.pre_checkout_duration_seconds",
            monotonic() - started,
            tags={"outcome": outcome},
        )


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None or message.successful_payment is None:
        return
    language = await _language(session, message.from_user.id)
    payment = message.successful_payment
    result = await PaymentService(session, settings).complete_payment(
        telegram_id=message.from_user.id,
        invoice_payload=payment.invoice_payload,
        currency=payment.currency,
        total_amount=payment.total_amount,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
        provider_payment_charge_id=payment.provider_payment_charge_id,
    )
    if result.processed and result.balance is not None:
        await message.answer(
            t(
                Msg.PAYMENT_SUCCESS,
                language,
                credits=result.credits,
                balance=result.balance,
            )
        )
    else:
        await message.answer(t(Msg.PAYMENT_REVIEW, language))


@router.message(Command("terms"))
async def on_terms(
    message: Message,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    language = await _language(session, message.from_user.id)
    if not settings.payment_terms_url.strip():
        await message.answer(t(Msg.PAYMENT_UNAVAILABLE, language))
        return
    await message.answer(t(Msg.PAYMENT_TERMS_TEXT, language, url=settings.payment_terms_url))
