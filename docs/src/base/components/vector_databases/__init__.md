# `src/base/components/vector_databases/__init__.py`

## Purpose

Exports the vector-database contract and provides the default ChromaDB factory.

## Responsibilities

- Re-export `BaseVectorDatabase`.
- Construct `ChromaVectorDatabase` with an embedding provider and collection name.
- Limit wildcard exports to the abstract interface and factory.

## Non-responsibilities

No ChromaDB configuration, connection check, collection operation, embedding request, or persistence logic is implemented here.

## Key types and functions

- `create_vector_database(embedding, collection_name="default") -> BaseVectorDatabase`: returns a `ChromaVectorDatabase` typed as the abstract interface.
- `BaseVectorDatabase`: vector-store contract.
- `ChromaVectorDatabase`: imported concrete implementation but intentionally omitted from `__all__`.

## Invariants and errors

The supplied embedding object is forwarded unchanged. Constructor and settings failures from `ChromaVectorDatabase` propagate.

## Dependencies

- `BaseEmbedding` for the factory input.
- `vector_databases.base` for `BaseVectorDatabase`.
- `vector_databases.chromadb` for the concrete default.

## Tests

No direct factory test; `src.container` constructs the application vector database through this entry point.

## Status

Implemented.
