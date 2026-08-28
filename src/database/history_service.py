"""Asynchronous conversation-history service."""

from loguru import logger

from src.database.postgres_manager import PostgresManager
from src.domain.models import DomainLabel, RiskLevel


class HistoryService:
    """Maps persisted conversation turns to OpenAI-compatible messages."""

    def __init__(self, database: PostgresManager | None = None) -> None:
        self._database = database or PostgresManager()

    async def connect(self) -> None:
        await self._database.connect()

    async def close(self) -> None:
        await self._database.close()

    async def healthcheck(self) -> None:
        await self.connect()
        await self._database.healthcheck()

    async def claim_conversation(self, conversation_id: str, *, owner_id: str) -> bool:
        await self.connect()
        return await self._database.claim_conversation(
            conversation_id, owner_id=owner_id
        )

    async def get_conversation_owner(self, conversation_id: str) -> str | None:
        await self.connect()
        return await self._database.get_conversation_owner(conversation_id)

    async def get_history(
        self,
        conversation_id: str,
        limit: int = 10,
        *,
        owner_id: str = "local-development",
    ) -> list[dict[str, str]]:
        await self.connect()
        turns = await self._database.get_conversation(
            conversation_id, limit, owner_id=owner_id
        )
        messages: list[dict[str, str]] = []
        for turn in turns:
            messages.extend(
                [
                    {"role": "user", "content": turn.query},
                    {"role": "assistant", "content": turn.answer},
                ]
            )
        return messages

    async def get_latest_domain_label(
        self,
        conversation_id: str,
        *,
        owner_id: str = "local-development",
    ) -> DomainLabel | None:
        await self.connect()
        return await self._database.get_latest_domain_label(
            conversation_id, owner_id=owner_id
        )

    async def save_turn(
        self,
        conversation_id: str,
        query: str,
        answer: str,
        domain_label: DomainLabel,
        risk_level: RiskLevel,
        *,
        owner_id: str = "local-development",
    ) -> int:
        await self.connect()
        saved_turn = await self._database.insert_turn(
            conversation_id,
            query,
            answer,
            domain_label,
            risk_level,
            owner_id=owner_id,
        )
        logger.debug("Saved conversation {} turn {}", conversation_id, saved_turn.turn)
        return saved_turn.turn

    async def clear_history(
        self,
        conversation_id: str,
        *,
        owner_id: str = "local-development",
    ) -> int:
        await self.connect()
        return await self._database.delete_conversation(
            conversation_id, owner_id=owner_id
        )


_history_service: HistoryService | None = None


def get_history_service() -> HistoryService:
    global _history_service
    if _history_service is None:
        _history_service = HistoryService()
    return _history_service
