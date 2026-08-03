from aiogram import Router

from apps.bot.handlers import (
    chat,
    menu,
    navigation,
    payments,
    profile,
    start,
    subscriptions,
)


def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(navigation.router)
    root.include_router(profile.router)
    # Subscriptions and packs share Telegram's payment updates. Both routers filter on the
    # invoice payload prefix, so this order is for readability only — neither relies on it.
    root.include_router(subscriptions.router)
    root.include_router(payments.router)
    root.include_router(chat.router)
    root.include_router(menu.router)
    return root
