# `src/readiness.py`

## Purpose

Warms critical dependencies during startup and computes a sanitized runtime readiness report.

## Responsibilities

- Functionally check history storage, embedding, knowledge and figure stores, API-key
  configuration, and the LLM during startup.
- Require populated knowledge and figure indexes and warm the domain classifier
  before accepting requests.
- Retry startup warmup according to configured attempt and delay limits.
- Check dependencies independently at runtime and record only public status strings.
- Optionally require nonempty knowledge and figure indexes.

## Non-responsibilities

No application lifespan ownership, HTTP status selection, resource construction, or dependency repair.

## Key types and functions

- `ReadinessReport`: frozen, slotted dataclass with aggregate `ready` and per-check `checks`.
- `warmup_application(container, history) -> None`: retries the complete warmup sequence until it succeeds or exhausts attempts.
- `check_readiness(container, history, *, require_indexes=True) -> ReadinessReport`: runs all checks and returns sanitized statuses.

## Invariants and errors

- Synchronous health checks run via `asyncio.to_thread` so they do not block the event loop.
- Any failed warmup attempt restarts the complete ordered sequence; exhaustion raises `RuntimeError` chained from the last exception.
- Runtime checks catch and log each dependency error, recording `unavailable` without exposing exception details.
- The classifier is `ready` only after warmup; otherwise it is `not_warmed`.
- Required indexes are `ready`, `empty`, or `unavailable`. The aggregate is ready only when every recorded value equals `ready`.
- With `require_indexes=False`, index population checks are omitted, but store health checks still run.

## Dependencies

- `ApplicationContainer`, `HistoryService`, and `get_llm_client`.
- `asyncio`, dataclasses, callable typing, and Loguru.

## Tests

`tests/test_readiness.py` verifies the complete warmup call set and that empty required indexes make the report not ready. API route coverage consumes this report through the readiness endpoint.

## Status

Implemented.
