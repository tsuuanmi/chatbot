# `src/base/components/__init__.py`

## Purpose

Provides the consolidated public entry point for embedding and vector-database components.

## Responsibilities

- Re-export `BaseEmbedding` and `BaseVectorDatabase`.
- Re-export the `create_embedding` and `create_vector_database` factories.
- Restrict wildcard exports through `__all__`.

## Non-responsibilities

No component construction logic, configuration validation, embedding requests, or vector-store operations are implemented here.

## Key types and functions

- `BaseEmbedding`: abstract text-embedding interface.
- `BaseVectorDatabase`: abstract vector-store interface.
- `create_embedding`: constructs the configured llama.cpp embedding client.
- `create_vector_database`: constructs the ChromaDB implementation.

## Invariants and errors

The exported names are imported eagerly, so import-time dependency or configuration-module failures propagate unchanged.

## Dependencies

- `src.base.components.embeddings` for the embedding interface and factory.
- `src.base.components.vector_databases` for the vector-store interface and factory.

## Tests

No direct tests; application container construction imports the child component packages.

## Status

Implemented.
