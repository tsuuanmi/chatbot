"""Bounded model capacity for LAN requests."""

import asyncio
from collections.abc import AsyncGenerator

from fastapi import HTTPException, status

from src.config.settings import get_settings

_semaphore: asyncio.Semaphore | None = None
_semaphore_limit: int | None = None


def _get_semaphore(limit: int) -> asyncio.Semaphore:
    global _semaphore, _semaphore_limit
    if _semaphore is None or _semaphore_limit != limit:
        _semaphore = asyncio.Semaphore(limit)
        _semaphore_limit = limit
    return _semaphore


async def reserve_model_capacity() -> AsyncGenerator[None, None]:
    """Queue for a configured model slot, then fail with a retryable 429."""
    settings = get_settings()
    semaphore = _get_semaphore(settings.api_max_concurrent_requests)
    try:
        await asyncio.wait_for(
            semaphore.acquire(), timeout=settings.api_queue_timeout_seconds
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The chatbot is busy; retry shortly",
            headers={"Retry-After": "5"},
        ) from None
    try:
        yield
    finally:
        semaphore.release()
