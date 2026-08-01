from secrets import compare_digest

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from kelbet.config import Settings, get_settings
from kelbet.observability import export_metrics

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Pure process liveness: dependency checks belong to /api/v1/ready."""
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
async def metrics(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        settings = get_settings()
    if not settings.metrics_endpoint_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    token = settings.metrics_bearer_token.strip()
    if not settings.metrics_enabled or not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metrics endpoint is not configured",
        )
    expected = f"Bearer {token}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    exported = export_metrics()
    if exported is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metrics backend is not available",
        )
    payload, content_type = exported
    return Response(
        content=payload,
        headers={"Content-Type": content_type, "Cache-Control": "no-store"},
    )
