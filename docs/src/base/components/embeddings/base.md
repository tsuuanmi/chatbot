# `src/base/components/embeddings/base.py`

## Purpose

Defines the implementation-independent contract for converting text into numeric embedding vectors.

## Responsibilities

- Require single-text embedding support.
- Require ordered batch embedding support.

## Non-responsibilities

No model selection, networking, batching policy, vector-dimension validation, retries, or resource lifecycle management.

## Key types and functions

- `BaseEmbedding`: abstract base class.
- `embed(text: str) -> list[float]`: returns one vector for one string.
- `embed_batch(texts: list[str]) -> list[list[float]]`: returns vectors for a list of strings.

## Invariants and errors

Subclasses must implement both abstract methods before they can be instantiated. The interface does not define concrete error types or enforce output dimensions.

## Dependencies

- Python `abc` for `ABC` and `abstractmethod`.

## Tests

No direct contract tests; test doubles implementing this boundary are used by classifier, indexing, and retrieval code.

## Status

Implemented.
