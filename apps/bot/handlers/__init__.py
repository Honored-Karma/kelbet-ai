from aiogram import Router

from apps.bot.handlers import menu, profile, start


def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(profile.router)
    root.include_router(menu.router)
    return root
