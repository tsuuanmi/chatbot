"""Functional startup warmup and runtime readiness checks."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger

from src.api.auth import healthcheck_authentication
from src.container import ApplicationContainer
from src.database.history_service import HistoryService
from src.llm.client import get_llm_client


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, str]


async def warmup_application(
    container: ApplicationContainer,
    history: HistoryService,
) -> None:
    """Warm critical local dependencies before accepting requests."""
    attempts = container.settings.startup_max_attempts
    delay = container.settings.startup_retry_seconds
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            await history.healthcheck()
            await asyncio.to_thread(container.embedding.healthcheck)
            await asyncio.to_thread(container.vector_database.healthcheck)
            knowledge_count = await asyncio.to_thread(
                lambda: len(container.vector_database.list_ids())
            )
            figure_count = await asyncio.to_thread(
                container.figure_descriptions.healthcheck
            )
            if not knowledge_count or not figure_count:
                raise RuntimeError("Required indexes are empty")
            await asyncio.to_thread(healthcheck_authentication)
            await get_llm_client().healthcheck()
            await container.domain_classifier.warmup()
            logger.info("Application dependency warmup completed")
            return
        except Exception as error:
            last_error = error
            if attempt == attempts:
                logger.exception(
                    "Application dependency warmup failed after {} attempts", attempts
                )
                logger.error(
                    "Check the postgres, chromadb, llama-server, and embedding-server "
                    "containers and their logs before retrying"
                )
                break
            logger.warning(
                "Application dependency warmup attempt {}/{} failed: {} ({}); retrying",
                attempt,
                attempts,
                error,
                type(error).__name__,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Application dependencies are not ready") from last_error


async def check_readiness(
    container: ApplicationContainer,
    history: HistoryService,
    *,
    require_indexes: bool = True,
) -> ReadinessReport:
    """Check every local dependency without exposing internal error details."""
    checks: dict[str, str] = {}

    async def check_async(name: str, operation: Callable[[], Awaitable[None]]) -> None:
        try:
            await operation()
            checks[name] = "ready"
        except Exception:
            logger.exception("Readiness check failed: {}", name)
            checks[name] = "unavailable"

    async def check_sync(name: str, operation: Callable[[], object]) -> None:
        try:
            await asyncio.to_thread(operation)
            checks[name] = "ready"
        except Exception:
            logger.exception("Readiness check failed: {}", name)
            checks[name] = "unavailable"

    await check_async("postgres", history.healthcheck)
    await check_sync("embedding", container.embedding.healthcheck)
    await check_async("llm", get_llm_client().healthcheck)
    await check_sync("knowledge_store", container.vector_database.healthcheck)
    await check_sync("figure_store", container.figure_descriptions.healthcheck)
    await check_sync("authentication", healthcheck_authentication)

    checks["classifier"] = (
        "ready" if container.domain_classifier.is_ready else "not_warmed"
    )
    if require_indexes:
        try:
            knowledge_count = await asyncio.to_thread(
                lambda: len(container.vector_database.list_ids())
            )
            checks["knowledge_index"] = "ready" if knowledge_count else "empty"
        except Exception:
            logger.exception("Readiness check failed: knowledge_index")
            checks["knowledge_index"] = "unavailable"
        try:
            figure_count = await asyncio.to_thread(
                container.figure_descriptions.healthcheck
            )
            checks["figure_index"] = "ready" if figure_count else "empty"
        except Exception:
            logger.exception("Readiness check failed: figure_index")
            checks["figure_index"] = "unavailable"

    return ReadinessReport(
        ready=all(status == "ready" for status in checks.values()),
        checks=checks,
    )
