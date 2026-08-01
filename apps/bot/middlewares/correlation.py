"""Bind one safe correlation id to every Telegram update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from kelbet.observability import correlation_context


class CorrelationIdMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        correlation_id = str(uuid4())
        data["correlation_id"] = correlation_id
        with correlation_context(correlation_id):
            return await handler(event, data)
