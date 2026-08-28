# `src/figures/__init__.py`

## Purpose

Defines the public interface for precomputed figure descriptions.

## Responsibilities

- Re-export the description prompt, model, indexer, and store.

## Non-responsibilities

No figure loading, generation, or persistence execution.

## Key types and functions

- `FIGURE_DESCRIPTION_PROMPT`, `FigureDescription`, `FigureDescriptionIndexer`, and `FigureDescriptionStore`.

## Invariants and errors

`__all__` enumerates the four supported package exports. Import-time dependency errors propagate.

## Dependencies

- `src.figures.indexer`, `src.figures.models`, and `src.figures.store`.

## Tests

Exports are exercised indirectly by `tests/test_indexing.py`; no dedicated initializer tests.

## Status

Implemented.
