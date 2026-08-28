# `src/figures/store.py`

## Purpose

Provides the persistence boundary for precomputed figure descriptions.

## Responsibilities

- Map figure IDs to stable vector-database document IDs.
- Health-check the database and report the reachable record count.
- Reconstruct typed descriptions from stored content and metadata.
- Delete stale figure records and upsert only changed descriptions.

## Non-responsibilities

No description generation, figure loading, embedding implementation, or semantic search.

## Key types and functions

- `FIGURE_SOURCE`: metadata source marker, `"figures"`.
- `FigureDescriptionStore.healthcheck()`: delegates readiness and counts listed IDs.
- `get()`: retrieves `figure:<figure_id>` and validates required string metadata.
- `save()`: removes IDs absent from the configured set and upserts supplied descriptions.
- `_document_id()`: builds the stable `figure:`-prefixed identifier.

## Invariants and errors

- Stored document IDs use `figure:<figure_id>`.
- `get()` returns `None` for missing records or non-string `content_hash`/`figure_id` metadata.
- `save()` treats every listed database ID outside the expected figure-ID set as stale; the database instance must therefore be scoped to figure records.
- Empty delete/upsert batches are delegated as-is to the database implementation.
- Vector-database errors propagate.

## Dependencies

- `BaseVectorDatabase` for health, exact lookup, listing, deletion, and upsert.
- `FigureDescription` for typed records.

## Tests

`tests/test_indexing.py` covers saving, exact retrieval, metadata reconstruction, and stale-record deletion with a vector-database test double.

## Status

Implemented.
