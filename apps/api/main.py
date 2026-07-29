from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.routes.health import router as health_router
from kelbet.config import get_settings
from kelbet.db.session import build_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.session_factory = build_session_factory(settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="KELBET AI API", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    return app
