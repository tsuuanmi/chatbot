"""Functional readiness and bounded-capacity tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api import capacity
from src.readiness import check_readiness, warmup_application


def ready_dependencies():
    settings = SimpleNamespace(startup_max_attempts=1, startup_retry_seconds=0.01)
    embedding = MagicMock()
    vector_database = MagicMock()
    vector_database.list_ids.return_value = ["knowledge:1"]
    figures = MagicMock()
    figures.healthcheck.return_value = 1
    classifier = MagicMock()
    classifier.is_ready = True
    classifier.warmup = AsyncMock()
    container = SimpleNamespace(
        settings=settings,
        embedding=embedding,
        vector_database=vector_database,
        figure_descriptions=figures,
        domain_classifier=classifier,
    )
    history = MagicMock()
    history.healthcheck = AsyncMock()
    llm = MagicMock()
    llm.healthcheck = AsyncMock()
    return container, history, llm


@pytest.mark.asyncio
async def test_application_warmup_functionally_checks_and_warms_dependencies() -> None:
    container, history, llm = ready_dependencies()
    with (
        patch("src.readiness.get_llm_client", return_value=llm),
        patch("src.readiness.healthcheck_authentication"),
    ):
        await warmup_application(container, history)

    history.healthcheck.assert_awaited_once()
    container.embedding.healthcheck.assert_called_once()
    container.vector_database.healthcheck.assert_called_once()
    container.figure_descriptions.healthcheck.assert_called_once()
    llm.healthcheck.assert_awaited_once()
    container.domain_classifier.warmup.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_requires_nonempty_indexes() -> None:
    container, history, llm = ready_dependencies()
    container.vector_database.list_ids.return_value = []
    container.figure_descriptions.healthcheck.return_value = 0
    with (
        patch("src.readiness.get_llm_client", return_value=llm),
        patch("src.readiness.healthcheck_authentication"),
    ):
        report = await check_readiness(container, history)

    assert not report.ready
    assert report.checks["knowledge_index"] == "empty"
    assert report.checks["figure_index"] == "empty"


@pytest.mark.asyncio
async def test_capacity_timeout_returns_retryable_429() -> None:
    settings = SimpleNamespace(
        api_max_concurrent_requests=1,
        api_queue_timeout_seconds=0.01,
    )
    capacity._semaphore = None
    capacity._semaphore_limit = None
    with patch("src.api.capacity.get_settings", return_value=settings):
        first = capacity.reserve_model_capacity()
        second = capacity.reserve_model_capacity()
        await anext(first)
        with pytest.raises(HTTPException) as raised:
            await anext(second)
        await first.aclose()

    assert raised.value.status_code == 429
    assert raised.value.headers == {"Retry-After": "5"}
