# `src/figures/models.py`

## Purpose

Defines the immutable record for a generated figure description.

## Responsibilities

- Keep a figure identifier, source-content hash, and natural-language description together.

## Non-responsibilities

No validation, hashing, generation, loading, or persistence.

## Key types and functions

- `FigureDescription`: frozen, slotted dataclass with `figure_id`, `content_hash`, and `description` strings.

## Invariants and errors

Instances are immutable and reject undeclared attributes because the dataclass is frozen and slotted. Runtime construction does not enforce non-empty strings.

## Dependencies

- Python `dataclasses.dataclass`.

## Tests

`tests/test_indexing.py` constructs and compares records while testing the store and indexer.

## Status

Implemented.
