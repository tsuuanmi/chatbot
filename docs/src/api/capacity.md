# `src/api/capacity.py`

## Purpose

Bounds concurrent model-backed API work and applies a configurable finite queue timeout.

## Responsibilities

- Maintain one process-local `asyncio.Semaphore` for the configured concurrency limit.
- Recreate the semaphore when the configured limit changes.
- Expose a FastAPI yield dependency that acquires a slot, yields to the request, and always releases it.
- Return a retryable HTTP 429 when no slot becomes available before the queue timeout.

## Non-responsibilities

No distributed capacity coordination, per-client quotas, request cancellation policy, or model execution.

## Key types and functions

- `_get_semaphore(limit) -> asyncio.Semaphore`: returns the cached semaphore for the requested limit.
- `reserve_model_capacity() -> AsyncGenerator[None, None]`: FastAPI dependency managing one model slot.

## Invariants and errors

- A successfully acquired slot is released in `finally`, including when request processing fails.
- Queue timeout raises `HTTPException` 429 with `Retry-After: 5` and a generic busy message.
- Deployment configuration sets capacity. The offline 6 GB GPU profile serializes generation and permits a 900-second wait so five LAN clients can queue safely; CPU uses the same conservative initial setting pending target measurements.
- Capacity is process-local; multiple worker processes do not share the semaphore.

## Dependencies

- `asyncio`.
- FastAPI `HTTPException` and status constants.
- `src.config.settings.get_settings`.

## Tests

`tests/test_readiness.py::test_capacity_timeout_returns_retryable_429` verifies that a second request times out at capacity and receives the expected 429 and retry header.

## Status

Implemented.
