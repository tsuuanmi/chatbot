# `src/base/components/embeddings/llamacpp.py`

## Purpose

Implements embeddings through a llama.cpp server's OpenAI-compatible `/embeddings` endpoint.

## Responsibilities

- Create a synchronous `httpx.Client` using configured base URL, bearer token, and a 60-second timeout.
- Submit single or batch embedding requests with the configured model name.
- Restore response order by each item's `index` field.
- Reject missing, empty, or count-mismatched vectors.
- Expose a health check and explicit client shutdown.

## Non-responsibilities

No retry policy, asynchronous transport, input chunking, vector normalization, dimension checks, or server process management.

## Key types and functions

- `LlamaCppEmbedding(settings=None)`: uses explicit settings or cached project settings.
- `embed(text)`: delegates to `embed_batch` and returns the first vector.
- `embed_batch(texts)`: posts to `/embeddings`, checks HTTP status, orders data, and validates vector presence/count.
- `healthcheck()`: embeds `"health check"` and rejects an empty vector.
- `close()`: closes the underlying synchronous HTTP client.

## Invariants and errors

- The server response must contain a `data` sequence whose items provide `index` and `embedding`.
- The number of non-empty returned vectors must equal the number of input texts; otherwise `RuntimeError` is raised.
- HTTP failures propagate from `httpx.Response.raise_for_status`; malformed JSON or missing fields propagate their native exceptions.
- `embed` assumes the batch call returns at least one vector.

## Dependencies

- `httpx` for synchronous HTTP transport.
- `BaseEmbedding` for the component contract.
- `Settings` and `get_settings` for endpoint, API key, and model configuration.

## Tests

No direct unit test currently covers this client; readiness and container code consume its health-check interface.

## Status

Implemented.
