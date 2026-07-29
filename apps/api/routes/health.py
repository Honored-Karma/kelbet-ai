from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
