"""PostgreSQL manager unit tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.postgres_manager import PostgresManager
from src.domain.models import DomainLabel, RiskLevel


def test_migration_preserves_existing_decisions_and_reserves_legacy_owner() -> None:
    migration = PostgresManager._CREATE_TABLE
    assert "SET owner_id = '__legacy__' WHERE owner_id IS NULL" in migration
    assert (
        "SET domain_label = 'IN_DOMAIN'\n        WHERE domain_label IS NULL"
        in migration
    )
    assert "SET risk_level = 'STANDARD'\n        WHERE risk_level IS NULL" in migration
    assert "SET owner_id = '__legacy__', domain_label" not in migration


@pytest.mark.asyncio
async def test_insert_turn_is_atomic_and_persists_decision() -> None:
    connection = AsyncMock()
    connection.fetchval.side_effect = ["client-a", 2]
    connection.fetchrow.return_value = {
        "owner_id": "client-a",
        "conversation_id": "conversation",
        "turn": 2,
        "query": "Question",
        "answer": "Answer",
        "domain_label": "IN_DOMAIN",
        "risk_level": "STANDARD",
        "created_at": None,
    }
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    connection.transaction = MagicMock(return_value=transaction)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=connection)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = acquire

    manager = PostgresManager("postgresql://localhost/test")
    manager._pool = pool
    turn = await manager.insert_turn(
        "conversation",
        "Question",
        "Answer",
        DomainLabel.IN_DOMAIN,
        RiskLevel.STANDARD,
        owner_id="client-a",
    )

    assert turn.turn == 2
    assert turn.owner_id == "client-a"
    assert turn.domain_label is DomainLabel.IN_DOMAIN
    assert connection.execute.await_args.args[0].startswith(
        "SELECT pg_advisory_xact_lock"
    )
    assert connection.execute.await_args.args[1] == "client-a:conversation"
    assert connection.fetchval.await_args.args[1:] == ("client-a", "conversation")


@pytest.mark.asyncio
async def test_delete_releases_zero_turn_conversation_owner() -> None:
    connection = AsyncMock()
    connection.execute.side_effect = ["SELECT 1", "DELETE 0", "DELETE 1"]
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    connection.transaction = MagicMock(return_value=transaction)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=connection)
    acquire.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire.return_value = acquire
    manager = PostgresManager("postgresql://localhost/test")
    manager._pool = pool

    deleted = await manager.delete_conversation("conversation", owner_id="client-a")

    assert deleted == 0
    assert "DELETE FROM conversation_owners" in connection.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_latest_domain_label_uses_latest_turn() -> None:
    pool = AsyncMock()
    pool.fetchval.return_value = "IN_DOMAIN"
    manager = PostgresManager("postgresql://localhost/test")
    manager._pool = pool

    label = await manager.get_latest_domain_label("conversation", owner_id="client-a")

    assert label is DomainLabel.IN_DOMAIN
    assert "owner_id = $1" in pool.fetchval.await_args.args[0]
    assert "ORDER BY turn DESC" in pool.fetchval.await_args.args[0]
    assert pool.fetchval.await_args.args[1:] == ("client-a", "conversation")


@pytest.mark.asyncio
async def test_requires_connected_pool() -> None:
    manager = PostgresManager("postgresql://localhost/test")
    with pytest.raises(RuntimeError, match="not connected"):
        await manager.get_conversation("conversation")
