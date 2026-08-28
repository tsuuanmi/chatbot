# `src/database/history_service.py`

## Purpose

Provides the asynchronous service boundary used to manage conversation history.

## Responsibilities

- Lazily connect the underlying `PostgresManager` before each operation.
- Claim conversations and expose their owner.
- Convert stored turns into OpenAI-compatible user/assistant message dictionaries.
- Read the latest domain label, save typed turns, clear history, and perform health checks.
- Provide a process-local singleton through `get_history_service()`.

## Non-responsibilities

No SQL, schema management, authentication, domain classification, or response generation.

## Key types and functions

- `HistoryService`: wraps persistence operations and history-message conversion.
- `connect()` / `close()` / `healthcheck()`: manage and verify database availability.
- `claim_conversation()` / `get_conversation_owner()`: mediate conversation ownership.
- `get_history()`: expands each persisted turn into one user and one assistant message.
- `get_latest_domain_label()`, `save_turn()`, and `clear_history()`: typed history operations.
- `get_history_service()`: lazily creates and returns the module singleton.

## Invariants and errors

- Returned history preserves the turn order supplied by `PostgresManager` and emits exactly two messages per turn.
- The default owner is `local-development` unless explicitly overridden.
- Database connection, ownership, and persistence errors propagate from `PostgresManager`.
- The singleton is process-local and is not reset by `close()`.

## Dependencies

- `src.database.postgres_manager.PostgresManager` for persistence.
- `src.domain.models` for `DomainLabel` and `RiskLevel`.
- Loguru for save diagnostics.

## Tests

Importability is checked in `tests/test_imports.py`. Persistence behavior beneath the service is exercised in `tests/test_postgres.py`; there are no dedicated `HistoryService` unit tests.

## Status

Implemented.
