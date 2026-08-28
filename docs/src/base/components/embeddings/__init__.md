# `src/base/components/embeddings/__init__.py`

## Purpose

Exports the embedding contract and creates the project's llama.cpp-backed embedding client.

## Responsibilities

- Re-export `BaseEmbedding` and `LlamaCppEmbedding`.
- Build a `LlamaCppEmbedding` from an explicit `Settings` instance.
- Define the package's wildcard-export surface.

## Non-responsibilities

No settings lookup, HTTP request, response validation, health checking, or client shutdown occurs in this module.

## Key types and functions

- `create_embedding(settings: Settings) -> LlamaCppEmbedding`: passes the supplied settings to the concrete client.
- `BaseEmbedding`: abstract embedding contract.
- `LlamaCppEmbedding`: OpenAI-compatible HTTP implementation.

## Invariants and errors

The factory requires a `Settings` argument and performs no validation itself; constructor and import failures propagate.

## Dependencies

- `embeddings.base` for `BaseEmbedding`.
- `embeddings.llamacpp` for `LlamaCppEmbedding`.
- `src.config.settings.Settings` for factory input typing.

## Tests

No direct tests; `src.container` uses this factory during dependency construction.

## Status

Implemented.
