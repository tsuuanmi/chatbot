# `src/api/sse_formatter.py`

## Purpose

Serializes typed chat-stream chunks as server-sent events (SSE).

## Responsibilities

- Convert a `StreamingChatChunk` to compact Pydantic JSON.
- Omit fields whose values are `None`.
- Wrap the JSON in one SSE `data:` record terminated by a blank line.

## Non-responsibilities

No stream iteration, event construction, error recovery, or HTTP response setup.

## Key types and functions

- `format_sse(chunk) -> str`: returns `data: <json>\n\n` for one chunk.

## Invariants and errors

- Every returned event contains exactly one `data:` line and the SSE record terminator.
- Pydantic serialization errors propagate to the caller.

## Dependencies

- `src.common.schemas.StreamingChatChunk`.

## Tests

`tests/test_api.py::test_chat_stream_uses_one_json_sse_format` exercises the formatter through the streaming endpoint and parses each `data:` line as JSON.

## Status

Implemented.
