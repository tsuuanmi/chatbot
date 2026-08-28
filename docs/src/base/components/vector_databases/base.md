# `src/base/components/vector_databases/base.py`

## Purpose

Defines the vector-store boundary and the common search-result record used by retrieval and indexing code.

## Responsibilities

- Store the embedding dependency shared by implementations.
- Define contracts for source replacement, upsert, exact lookup, ID listing, semantic and lexical search, and deletion.
- Provide a default reachability health check through `list_ids()`.
- Represent search results consistently.

## Non-responsibilities

No persistence engine, collection naming, embedding generation policy, ranking algorithm, metadata schema, or transaction behavior is implemented here.

## Key types and functions

- `SearchHit`: frozen, slotted dataclass containing `id`, `content`, arbitrary `metadata`, and numeric `distance`.
- `BaseVectorDatabase(embedding)`: abstract base class retaining a `BaseEmbedding`.
- `healthcheck()`: calls `list_ids` and discards the result.
- `replace_source`, `upsert`, `get_by_id`, `list_ids`, `similarity_search`, `lexical_search`, and `delete`: required implementation methods.

## Invariants and errors

Concrete subclasses must implement every abstract method. The contract does not validate list lengths, metadata shape, `k`, or distance semantics, and it defines no custom exceptions; implementation errors propagate.

## Dependencies

- Python `abc` for the abstract contract.
- `dataclasses` for immutable `SearchHit` values.
- `typing.Any` for backend-defined metadata.
- `BaseEmbedding` for query and document embeddings.

## Tests

- `tests/test_knowledge.py` uses `SearchHit` to verify retrieval filtering.
- `tests/test_indexing.py` uses `SearchHit` and mocked interface methods to verify figure storage and indexing behavior.

## Status

Implemented.
