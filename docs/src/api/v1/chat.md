# `src/api/v1/chat.py`

## Purpose

Implements authenticated non-streaming and SSE chat requests plus client-scoped conversation deletion.

## Responsibilities

- Assign a UUID when the request omits a conversation ID.
- Claim conversations for the authenticated client before workflow execution.
- Reserve bounded model capacity for both chat execution modes.
- Run the workflow and shape typed non-streaming responses.
- Stream start, token chunk, end, and sanitized error events over SSE.
- Persist successful nonempty answers with domain and risk metadata without failing the response when persistence fails.
- Return only citations both present in evidence and referenced by the final answer.
- Prevent clients from reading or deleting another client's conversation by returning a non-disclosing 404.

## Non-responsibilities

No request-schema validation, authentication implementation, workflow logic, citation extraction rules, capacity implementation, or history storage implementation.

## Key types and functions

- `chat(request, client, capacity) -> ChatResponse`: runs the complete workflow and returns one response.
- `stream_chat(request, client, capacity) -> StreamingResponse`: starts the workflow and streams JSON SSE records.
- `_claim_conversation(history, conversation_id, owner_id) -> None`: enforces client ownership or raises 404.
- `_citations(state) -> list[Citation]`: filters evidence to IDs recorded as used.
- `_decision(state) -> tuple[DomainLabel, RiskLevel]`: returns workflow classification or the in-domain/standard fallback.
- `clear_history(conversation_id, client) -> dict`: clears the caller's conversation turns and reports the count.

## Invariants and errors

- A workflow result must contain a non-`None` response source; otherwise a `RuntimeError` is raised.
- Persistence failures are logged and do not fail a completed chat or stream.
- Streaming ignores empty tokens, computes used citation IDs from the joined answer, and emits an `end` event after normal completion.
- Exceptions raised while iterating the event generator are logged and converted to a generic SSE `error` event; the error text does not expose internals.
- Stream responses disable caching and proxy buffering and use `text/event-stream`.
- Ownership mismatch is deliberately indistinguishable from an absent conversation.

## Dependencies

- FastAPI routing/dependencies/errors and `StreamingResponse`.
- API authentication, capacity, and SSE formatting.
- Chat schemas, history service, workflow graph, state/domain models, and citation extraction.
- UUID generation and Loguru.

## Tests

`tests/test_api.py` verifies response shape, generated IDs, ownership denial, validation behavior, SSE event order/content, persistence, deletion, and removal of legacy endpoints. `tests/test_integration.py` and `tests/test_performance.py` exercise deployed chat and streaming behavior.

## Status

Implemented.
