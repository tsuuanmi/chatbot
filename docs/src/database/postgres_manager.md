# `src/database/postgres_manager.py`

## Purpose

Persists owned conversation turns in PostgreSQL through an asynchronous connection pool.

## Responsibilities

- Normalize configured asyncpg URLs and own the `asyncpg` pool lifecycle.
- Create and migrate conversation and ownership tables on connection.
- Atomically claim globally unique conversation IDs for owners.
- Insert monotonically numbered turns under an advisory transaction lock.
- Read recent turns in chronological order, read the latest domain label, delete conversations, and check readiness.

## Non-responsibilities

No authentication, history-to-chat conversion, domain classification, or retry policy.

## Key types and functions

- `ConversationTurn`: Pydantic record containing owner, conversation, turn number, query, answer, labels, risk, and optional creation time.
- `PostgresManager.connect()` / `close()`: initialize or close the pool.
- `healthcheck()`: require `SELECT 1` to return `1`.
- `claim_conversation()` and `_claim_conversation()`: reserve a conversation ID without transferring existing ownership.
- `insert_turn()`: lock the owner/conversation pair, claim ownership, assign the next
  turn, and return it.
- `get_conversation()`: fetch the newest limited window and reverse it into chronological order.
- `get_latest_domain_label()` and `delete_conversation()`: query label state and remove owned history.
- `_require_pool()`: enforce connection before database operations.

## Invariants and errors

- `(owner_id, conversation_id, turn)` is the conversation primary key; `conversation_id` is unique in `conversation_owners`.
- Existing conversation ownership is never reassigned by a claim.
- Turn allocation is serialized per owner/conversation with a PostgreSQL advisory transaction lock.
- Calling pool-dependent methods before `connect()` raises `RuntimeError`.
- Inserting under another owner raises `RuntimeError("Conversation belongs to another client")`.
- A failed readiness query raises `RuntimeError`; asyncpg and Pydantic errors otherwise propagate.
- Legacy rows receive the reserved, non-client owner `__legacy__`; existing labels
  and risk values are preserved, while only missing values are backfilled.

## Dependencies

- `asyncpg` for pooling, transactions, and SQL execution.
- `src.config.settings.get_settings` for the default database URL.
- `src.domain.models` for stored enums.
- Pydantic for row validation and Loguru for lifecycle logging.

## Tests

`tests/test_postgres.py` covers migration invariants, insertion, zero-turn owner
release, latest-label lookup, and disconnected-manager failure using mocked asyncpg
behavior. API tests also consume the persistence interface.

## Status

Implemented.
