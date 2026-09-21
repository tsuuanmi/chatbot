"""Bounded admission control for expensive model generation."""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator


class GenerationBusyError(RuntimeError):
    """Raised when no generation slot becomes available in time."""

    def __init__(
        self,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(
            "model generation capacity is busy"
        )

        self.retry_after_seconds = (
            retry_after_seconds
        )


class GenerationAdmissionController:
    """Bound concurrent access to llama.cpp generation."""

    def __init__(
        self,
        *,
        limit: int = 1,
        queue_timeout_seconds: float = 5.0,
    ) -> None:
        if limit < 1:
            raise ValueError(
                "generation limit must be positive"
            )

        if queue_timeout_seconds <= 0:
            raise ValueError(
                "generation queue timeout must be positive"
            )

        self.limit = limit
        self.queue_timeout_seconds = (
            queue_timeout_seconds
        )

        self.retry_after_seconds = max(
            1,
            math.ceil(
                queue_timeout_seconds
            ),
        )

        self._semaphore = asyncio.Semaphore(
            limit
        )

    @asynccontextmanager
    async def slot(
        self,
    ) -> AsyncIterator[None]:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=(
                    self.queue_timeout_seconds
                ),
            )

        except asyncio.TimeoutError as error:
            raise GenerationBusyError(
                self.retry_after_seconds
            ) from error

        try:
            yield

        finally:
            self._semaphore.release()
