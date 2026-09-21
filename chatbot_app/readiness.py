"""Production dependency readiness checks."""

from __future__ import annotations

import asyncio
import os
import urllib.request
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from chatbot_app.database import (
    postgres_connection_string,
)


class DatabaseReadinessChecker:
    """Verify database resources required by the running application."""

    def __init__(self) -> None:
        self._pool = AsyncConnectionPool(
            conninfo=postgres_connection_string(),
            min_size=0,
            max_size=1,
            open=False,
            kwargs={
                "row_factory": dict_row,
            },
            name="readiness",
        )

        self._started = False
        self._start_lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._started:
            return

        async with self._start_lock:
            if self._started:
                return

            await self._pool.open()
            self._started = True

    async def check(self) -> None:
        await self.connect()

        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    EXISTS (
                        SELECT 1
                        FROM pg_extension
                        WHERE extname = 'vector'
                    ) AS vector_ready,
                    to_regclass(
                        'public.conversations'
                    ) IS NOT NULL AS conversations_ready,
                    to_regclass(
                        'public.conversation_turns'
                    ) IS NOT NULL AS conversation_turns_ready,
                    to_regclass(
                        'public.knowledge_documents'
                    ) IS NOT NULL AS knowledge_documents_ready
                """
            )

            row = await cursor.fetchone()

            if row is None:
                raise RuntimeError(
                    "Database readiness query returned no row"
                )

            required = (
                "vector_ready",
                "conversations_ready",
                "conversation_turns_ready",
                "knowledge_documents_ready",
            )

            missing = [
                name
                for name in required
                if not bool(row[name])
            ]

            if missing:
                raise RuntimeError(
                    "Required database resources are missing: "
                    + ", ".join(missing)
                )

            cursor = await connection.execute(
                """
                SELECT COUNT(*) AS document_count
                FROM knowledge_documents
                """
            )

            count_row = await cursor.fetchone()

            if (
                count_row is None
                or int(count_row["document_count"]) < 1
            ):
                raise RuntimeError(
                    "Knowledge index is empty"
                )


class ReadinessService:
    """Verify dependencies required for normal chat operation."""

    def __init__(self) -> None:
        self.database = DatabaseReadinessChecker()

        base_url = os.environ[
            "LLAMA_BASE_URL"
        ].rstrip("/")

        if base_url.endswith("/v1"):
            base_url = base_url[:-3]

        self.llama_health_url = (
            f"{base_url}/health"
        )

    async def check(
        self,
    ) -> dict[str, str]:
        await asyncio.gather(
            self.database.check(),
            asyncio.to_thread(
                self._check_llama
            ),
        )

        return {
            "status": "ready",
            "database": "ok",
            "knowledge": "ok",
            "llama": "ok",
        }

    def _check_llama(self) -> None:
        request = urllib.request.Request(
            self.llama_health_url,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=3,
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    "llama.cpp readiness check failed"
                )


@lru_cache
def get_readiness() -> ReadinessService:
    return ReadinessService()
