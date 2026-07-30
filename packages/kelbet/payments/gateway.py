from __future__ import annotations

from typing import Protocol

from aiogram import Bot
from aiogram.types import LabeledPrice

from kelbet.domain.exceptions import PaymentUnavailableError
from kelbet.services.payment import PaymentOrderDTO


class PaymentInvoiceGateway(Protocol):
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str: ...


class AiogramStarsGateway:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        return await self._bot.create_invoice_link(
            title=order.product_name[:32],
            description=order.product_description[:255],
            payload=order.invoice_payload,
            currency=order.currency,
            prices=[
                LabeledPrice(
                    label=f"{order.credits} KELBET credits",
                    amount=order.total_amount,
                )
            ],
        )


class DisabledPaymentGateway:
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        raise PaymentUnavailableError("Telegram Stars gateway is disabled")


class MockPaymentGateway:
    async def create_invoice_link(self, order: PaymentOrderDTO) -> str:
        return f"https://t.me/$kelbet_{order.id.hex}"
