from fastapi import APIRouter

from apps.api.routes.v1.admin import router as admin_router
from apps.api.routes.v1.assets import router as assets_router
from apps.api.routes.v1.auth import router as auth_router
from apps.api.routes.v1.catalog import router as catalog_router
from apps.api.routes.v1.generations import router as generations_router
from apps.api.routes.v1.history import router as history_router
from apps.api.routes.v1.me import router as me_router
from apps.api.routes.v1.moderation import router as moderation_router
from apps.api.routes.v1.payments import router as payments_router
from apps.api.routes.v1.prompt_assistant import router as prompt_assistant_router
from apps.api.routes.v1.ready import router as ready_router
from apps.api.routes.v1.referrals import router as referrals_router
from apps.api.routes.v1.subscriptions import router as subscriptions_router
from apps.api.routes.v1.uploads import router as uploads_router
from apps.api.routes.v1.wallet import router as wallet_router
from apps.api.routes.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(admin_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(me_router)
api_v1_router.include_router(moderation_router)
api_v1_router.include_router(ready_router)
api_v1_router.include_router(referrals_router)
api_v1_router.include_router(catalog_router)
api_v1_router.include_router(wallet_router)
api_v1_router.include_router(payments_router)
api_v1_router.include_router(subscriptions_router)
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(assets_router)
api_v1_router.include_router(generations_router)
api_v1_router.include_router(history_router)
api_v1_router.include_router(prompt_assistant_router)
api_v1_router.include_router(webhooks_router)

__all__ = ["api_v1_router"]
