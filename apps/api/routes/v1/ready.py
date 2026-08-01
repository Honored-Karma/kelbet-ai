from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["ready"])


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    ok = True

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        checks["database"] = "missing"
        ok = False
    else:
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            ok = False

    redis = getattr(request.app.state, "redis", None)
    redis_required = bool(getattr(request.app.state, "readiness_require_redis", True))
    if redis is None:
        checks["redis"] = "missing" if redis_required else "skipped"
        if redis_required:
            ok = False
    else:
        try:
            pong = await redis.ping()
            checks["redis"] = "ok" if pong else "error"
            if not pong:
                ok = False
        except Exception:
            checks["redis"] = "error"
            ok = False

    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if ok else "degraded", "checks": checks},
    )
