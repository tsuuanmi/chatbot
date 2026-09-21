"""PostgreSQL-backed conversation persistence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from chatbot_app.database import (
    postgres_connection_string,
)


class ConversationOwnershipError(RuntimeError):
    """Raised when a conversation belongs to another owner."""


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    conversation_id: UUID
    turn: int
    query: str
    answer: str
    domain: str
    risk: str
    source: str
    created_at: datetime


class ConversationRepository:
    """Store complete user/assistant turns atomically."""

    def __init__(self) -> None:
        self._pool = AsyncConnectionPool(
            conninfo=postgres_connection_string(),
            min_size=1,
            max_size=4,
            open=False,
            kwargs={
                "row_factory": dict_row,
            },
            name="chat-history",
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

    async def healthcheck(self) -> None:
        await self.connect()

        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT 1 AS value"
            )

            row = await cursor.fetchone()

            if row is None or row["value"] != 1:
                raise RuntimeError(
                    "Conversation database healthcheck failed"
                )

    async def ensure_conversation(
        self,
        conversation_id: UUID,
        *,
        owner_id: str,
    ) -> None:
        await self.connect()

        async with self._pool.connection() as connection:
            async with connection.transaction():
                await self._ensure_conversation(
                    connection,
                    conversation_id,
                    owner_id,
                )

    async def append_turn(
        self,
        conversation_id: UUID,
        *,
        owner_id: str,
        query: str,
        answer: str,
        domain: str,
        risk: str,
        source: str,
    ) -> ConversationTurn:
        await self.connect()

        async with self._pool.connection() as connection:
            async with connection.transaction():
                # Serialize allocation and write for one
                # owner/conversation pair in the same transaction.
                await connection.execute(
                    """
                    SELECT pg_advisory_xact_lock(
                        hashtextextended(%s, 0)
                    )
                    """,
                    (
                        f"{owner_id}:{conversation_id}",
                    ),
                )

                await self._ensure_conversation(
                    connection,
                    conversation_id,
                    owner_id,
                )

                cursor = await connection.execute(
                    """
                    SELECT COALESCE(MAX(turn), 0) + 1 AS next_turn
                    FROM conversation_turns
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )

                row = await cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Unable to allocate conversation turn"
                    )

                next_turn = int(
                    row["next_turn"]
                )

                cursor = await connection.execute(
                    """
                    INSERT INTO conversation_turns (
                        conversation_id,
                        turn,
                        query,
                        answer,
                        domain,
                        risk,
                        source
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING
                        conversation_id,
                        turn,
                        query,
                        answer,
                        domain,
                        risk,
                        source,
                        created_at
                    """,
                    (
                        conversation_id,
                        next_turn,
                        query,
                        answer,
                        domain,
                        risk,
                        source,
                    ),
                )

                saved = await cursor.fetchone()

                if saved is None:
                    raise RuntimeError(
                        "Conversation turn insert returned no row"
                    )

                await connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = now()
                    WHERE id = %s
                    """,
                    (conversation_id,),
                )

        return self._to_turn(saved)

    async def get_turns(
        self,
        conversation_id: UUID,
        *,
        owner_id: str,
        limit: int = 6,
    ) -> list[ConversationTurn]:
        if limit < 1 or limit > 50:
            raise ValueError(
                "history limit must be between 1 and 50"
            )

        await self.connect()

        async with self._pool.connection() as connection:
            await self._require_owner(
                connection,
                conversation_id,
                owner_id,
            )

            cursor = await connection.execute(
                """
                SELECT
                    conversation_id,
                    turn,
                    query,
                    answer,
                    domain,
                    risk,
                    source,
                    created_at
                FROM conversation_turns
                WHERE conversation_id = %s
                ORDER BY turn DESC
                LIMIT %s
                """,
                (
                    conversation_id,
                    limit,
                ),
            )

            rows = await cursor.fetchall()

        return [
            self._to_turn(row)
            for row in reversed(rows)
        ]

    async def delete_conversation(
        self,
        conversation_id: UUID,
        *,
        owner_id: str,
    ) -> int:
        await self.connect()

        async with self._pool.connection() as connection:
            async with connection.transaction():
                cursor = await connection.execute(
                    """
                    SELECT owner_id
                    FROM conversations
                    WHERE id = %s
                    """,
                    (conversation_id,),
                )

                owner = await cursor.fetchone()

                if owner is None:
                    return 0

                if owner["owner_id"] != owner_id:
                    raise ConversationOwnershipError(
                        "Conversation belongs to another owner"
                    )

                cursor = await connection.execute(
                    """
                    SELECT COUNT(*) AS turn_count
                    FROM conversation_turns
                    WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )

                row = await cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Unable to count conversation turns"
                    )

                deleted_turns = int(
                    row["turn_count"]
                )

                await connection.execute(
                    """
                    DELETE FROM conversations
                    WHERE id = %s
                      AND owner_id = %s
                    """,
                    (
                        conversation_id,
                        owner_id,
                    ),
                )

        return deleted_turns
    async def _ensure_conversation(
        self,
        connection: AsyncConnection,
        conversation_id: UUID,
        owner_id: str,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO conversations (
                id,
                owner_id
            )
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                conversation_id,
                owner_id,
            ),
        )

        await self._require_owner(
            connection,
            conversation_id,
            owner_id,
        )

    @staticmethod
    async def _require_owner(
        connection: AsyncConnection,
        conversation_id: UUID,
        owner_id: str,
    ) -> None:
        cursor = await connection.execute(
            """
            SELECT owner_id
            FROM conversations
            WHERE id = %s
            """,
            (conversation_id,),
        )

        row = await cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "Conversation does not exist"
            )

        if row["owner_id"] != owner_id:
            raise ConversationOwnershipError(
                "Conversation belongs to another owner"
            )

    @staticmethod
    def _to_turn(
        row: dict[str, object],
    ) -> ConversationTurn:
        return ConversationTurn(
            conversation_id=row["conversation_id"],
            turn=int(row["turn"]),
            query=str(row["query"]),
            answer=str(row["answer"]),
            domain=str(row["domain"]),
            risk=str(row["risk"]),
            source=str(row["source"]),
            created_at=row["created_at"],
        )


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return ConversationRepository()
