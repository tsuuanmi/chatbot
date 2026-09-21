"""Runtime access to precomputed configured figure descriptions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from chatbot_app.database import (
    postgres_connection_string,
)


@dataclass(frozen=True, slots=True)
class FigureDescription:
    figure_id: str
    content_hash: str
    mime_type: str
    source_name: str
    description_version: int
    description: str


class FigureDescriptionRepository:
    """Read precomputed figure descriptions from PostgreSQL."""

    def __init__(self) -> None:
        self._pool = AsyncConnectionPool(
            conninfo=postgres_connection_string(),
            min_size=1,
            max_size=4,
            open=False,
            kwargs={
                "row_factory": dict_row,
            },
            name="figure-cache",
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
            await self._pool.wait(
                timeout=10.0
            )

            self._started = True

    async def get(
        self,
        figure_id: str,
    ) -> FigureDescription | None:
        await self.connect()

        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT
                    figure_id,
                    content_hash,
                    mime_type,
                    source_name,
                    description_version,
                    description
                FROM figure_descriptions
                WHERE figure_id = %s
                """,
                (figure_id,),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return FigureDescription(
            figure_id=str(
                row["figure_id"]
            ),
            content_hash=str(
                row["content_hash"]
            ),
            mime_type=str(
                row["mime_type"]
            ),
            source_name=str(
                row["source_name"]
            ),
            description_version=int(
                row["description_version"]
            ),
            description=str(
                row["description"]
            ),
        )


@lru_cache
def get_figure_repository() -> FigureDescriptionRepository:
    return FigureDescriptionRepository()
