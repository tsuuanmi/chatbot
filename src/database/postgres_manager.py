"""PostgreSQL persistence for conversation turns."""

from datetime import datetime

import asyncpg
from loguru import logger
from pydantic import BaseModel

from src.config.settings import get_settings
from src.domain.models import DomainLabel, RiskLevel


class ConversationTurn(BaseModel):
    owner_id: str
    conversation_id: str
    turn: int
    query: str
    answer: str
    domain_label: DomainLabel
    risk_level: RiskLevel
    created_at: datetime | None = None


class PostgresManager:
    """Owns the asyncpg pool and atomic conversation-turn operations."""

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS conversations (
            owner_id VARCHAR(64) NOT NULL,
            conversation_id VARCHAR(255) NOT NULL,
            turn INT NOT NULL,
            query TEXT NOT NULL,
            answer TEXT NOT NULL,
            domain_label VARCHAR(32),
            risk_level VARCHAR(32),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (owner_id, conversation_id, turn)
        );
        ALTER TABLE conversations ADD COLUMN IF NOT EXISTS owner_id VARCHAR(64);
        ALTER TABLE conversations ADD COLUMN IF NOT EXISTS domain_label VARCHAR(32);
        ALTER TABLE conversations ADD COLUMN IF NOT EXISTS risk_level VARCHAR(32);
        UPDATE conversations SET owner_id = '__legacy__' WHERE owner_id IS NULL;
        UPDATE conversations
        SET domain_label = 'IN_DOMAIN'
        WHERE domain_label IS NULL;
        UPDATE conversations
        SET risk_level = 'STANDARD'
        WHERE risk_level IS NULL;
        ALTER TABLE conversations ALTER COLUMN owner_id SET NOT NULL;
        ALTER TABLE conversations ALTER COLUMN domain_label SET NOT NULL;
        ALTER TABLE conversations ALTER COLUMN risk_level SET NOT NULL;
        ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_pkey;
        ALTER TABLE conversations ADD CONSTRAINT conversations_pkey
            PRIMARY KEY (owner_id, conversation_id, turn);
        CREATE TABLE IF NOT EXISTS conversation_owners (
            conversation_id VARCHAR(255) PRIMARY KEY,
            owner_id VARCHAR(64) NOT NULL
        );
        INSERT INTO conversation_owners (conversation_id, owner_id)
        SELECT conversation_id, MIN(owner_id)
        FROM conversations
        GROUP BY conversation_id
        ON CONFLICT (conversation_id) DO NOTHING;
    """

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or get_settings().database_url
        self.database_url = url.replace("postgresql+asyncpg://", "postgresql://")
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=10)
        try:
            async with pool.acquire() as connection:
                await connection.execute(self._CREATE_TABLE)
        except Exception:
            await pool.close()
            raise
        self._pool = pool
        logger.info("PostgreSQL connection pool initialized")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def healthcheck(self) -> None:
        pool = self._require_pool()
        value = await pool.fetchval("SELECT 1")
        if value != 1:
            raise RuntimeError("PostgreSQL readiness check failed")

    async def claim_conversation(self, conversation_id: str, *, owner_id: str) -> bool:
        """Atomically reserve a conversation ID for one authenticated client."""
        pool = self._require_pool()
        async with pool.acquire() as connection, connection.transaction():
            return await self._claim_conversation(connection, conversation_id, owner_id)

    async def get_conversation_owner(self, conversation_id: str) -> str | None:
        pool = self._require_pool()
        return await pool.fetchval(
            "SELECT owner_id FROM conversation_owners WHERE conversation_id = $1",
            conversation_id,
        )

    async def insert_turn(
        self,
        conversation_id: str,
        query: str,
        answer: str,
        domain_label: DomainLabel,
        risk_level: RiskLevel,
        *,
        owner_id: str = "local-development",
    ) -> ConversationTurn:
        pool = self._require_pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"{owner_id}:{conversation_id}",
            )
            if not await self._claim_conversation(
                connection, conversation_id, owner_id
            ):
                raise RuntimeError("Conversation belongs to another client")
            turn = await connection.fetchval(
                """
                SELECT COALESCE(MAX(turn), 0) + 1
                FROM conversations
                WHERE owner_id = $1 AND conversation_id = $2
                """,
                owner_id,
                conversation_id,
            )
            row = await connection.fetchrow(
                """
                INSERT INTO conversations (
                    owner_id, conversation_id, turn, query, answer,
                    domain_label, risk_level
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING owner_id, conversation_id, turn, query, answer,
                          domain_label, risk_level, created_at
                """,
                owner_id,
                conversation_id,
                turn,
                query,
                answer,
                domain_label,
                risk_level,
            )
        return ConversationTurn(**dict(row))

    async def get_conversation(
        self,
        conversation_id: str,
        limit: int = 10,
        *,
        owner_id: str = "local-development",
    ) -> list[ConversationTurn]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """
            SELECT owner_id, conversation_id, turn, query, answer,
                   domain_label, risk_level, created_at
            FROM conversations
            WHERE owner_id = $1 AND conversation_id = $2
            ORDER BY turn DESC
            LIMIT $3
            """,
            owner_id,
            conversation_id,
            limit,
        )
        return [ConversationTurn(**dict(row)) for row in reversed(rows)]

    async def get_latest_domain_label(
        self,
        conversation_id: str,
        *,
        owner_id: str = "local-development",
    ) -> DomainLabel | None:
        pool = self._require_pool()
        value = await pool.fetchval(
            """
            SELECT domain_label
            FROM conversations
            WHERE owner_id = $1 AND conversation_id = $2
            ORDER BY turn DESC
            LIMIT 1
            """,
            owner_id,
            conversation_id,
        )
        return DomainLabel(value) if value else None

    async def delete_conversation(
        self,
        conversation_id: str,
        *,
        owner_id: str = "local-development",
    ) -> int:
        pool = self._require_pool()
        async with pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"{owner_id}:{conversation_id}",
            )
            result = await connection.execute(
                "DELETE FROM conversations WHERE owner_id = $1 AND conversation_id = $2",
                owner_id,
                conversation_id,
            )
            deleted = int(result.rsplit(" ", 1)[-1])
            await connection.execute(
                "DELETE FROM conversation_owners WHERE owner_id = $1 AND conversation_id = $2",
                owner_id,
                conversation_id,
            )
        return deleted

    @staticmethod
    async def _claim_conversation(
        connection: asyncpg.Connection, conversation_id: str, owner_id: str
    ) -> bool:
        claimed_owner = await connection.fetchval(
            """
            INSERT INTO conversation_owners (conversation_id, owner_id)
            VALUES ($1, $2)
            ON CONFLICT (conversation_id) DO UPDATE
            SET owner_id = conversation_owners.owner_id
            RETURNING owner_id
            """,
            conversation_id,
            owner_id,
        )
        return claimed_owner == owner_id

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgreSQL manager is not connected")
        return self._pool
