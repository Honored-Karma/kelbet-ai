from __future__ import annotations

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
from kelbet.services.payment import PaymentService
from kelbet.services.profile import ProfileService
from kelbet.services.registration import RegistrationService

router = Router(name="payments")


def _payments_ready(settings: Settings) -> bool:
    return bool(
        settings.payments_enabled
        and settings.payment_terms_url.strip()
        and settings.support_username.strip().lstrip("@")
    )


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
    if not _payments_ready(settings):
        await message.answer(t(Msg.PAYMENT_UNAVAILABLE, language))
        return
    products = await PaymentService(session, settings).list_products(language)
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
                callback_data=f"pay_confirm:{product.slug}",
            )
        ]
        for product in products
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text=t(Msg.PAYMENT_TERMS_OPEN, language),
                url=settings.payment_terms_url,
            )
        ]
    )
    await message.answer(
        t(Msg.PAYMENT_CHOOSE, language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("pay_confirm:"))
async def on_payment_confirm(
    callback: CallbackQuery,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user is None or callback.data is None or callback.message is None:
        return
    language = await _language(session, callback.from_user.id)
    if not _payments_ready(settings):
        await callback.answer(t(Msg.PAYMENT_UNAVAILABLE, language), show_alert=True)
        return
    product_slug = callback.data.removeprefix("pay_confirm:")
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
    language = await _language(session, query.from_user.id)
    result = await PaymentService(session, settings).validate_pre_checkout(
        telegram_id=query.from_user.id,
        query_id=query.id,
        invoice_payload=query.invoice_payload,
        currency=query.currency,
        total_amount=query.total_amount,
    )
    if result.ok:
        await query.answer(ok=True)
    else:
        await query.answer(
            ok=False,
            error_message=t(Msg.PAYMENT_CHECKOUT_REJECTED, language),
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
