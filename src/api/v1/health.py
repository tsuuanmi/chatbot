"""Application liveness and dependency readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from src.api.auth import AuthenticatedClient, require_client
from src.config.settings import get_settings
from src.container import get_container
from src.database.history_service import get_history_service
from src.readiness import check_readiness

router = APIRouter(tags=["health"])


@router.get("/live")
@router.get("/health")
async def liveness() -> dict[str, str]:
    """Report only that the API process is running."""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness(
    response: Response,
    _client: Annotated[AuthenticatedClient, Depends(require_client)],
) -> dict[str, str | dict[str, str]]:
    """Report whether every local dependency and required index is usable."""
    report = await check_readiness(get_container(), get_history_service())
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if report.ready else "not_ready",
        "checks": report.checks,
    }


@router.get("/health/detailed")
async def detailed_health_check(
    _client: Annotated[AuthenticatedClient, Depends(require_client)],
) -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "healthy",
        "llm_model": settings.llama_model_name,
        "embedding_model": settings.embedding_model_name,
        "version": "0.2.3",
    }
