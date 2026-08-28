# `src/database/__init__.py`

## Purpose

Defines the public interface of the database package.

## Responsibilities

- Re-export `PostgresManager` and `ConversationTurn`.

## Non-responsibilities

No connection management, queries, or schema migration logic.

## Key types and functions

- `PostgresManager`: asynchronous PostgreSQL persistence manager.
- `ConversationTurn`: typed persisted conversation record.

## Invariants and errors

`__all__` limits the documented package exports to the two re-exported names. Import-time dependency errors propagate.

## Dependencies

- `src.database.postgres_manager`.

## Tests

Package imports are covered indirectly by database tests; no dedicated package-initializer tests.

## Status

Implemented.
