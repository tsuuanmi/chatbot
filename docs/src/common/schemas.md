# `src/common/schemas.py`

## Purpose

Defines validated Pydantic contracts for chat requests, responses, citations, and server-sent-event chunks.

## Responsibilities

- Constrain response-source and conversation-status vocabulary.
- Validate request field lengths and reject blank queries.
- Validate optional images as base64 payloads or base64 data URLs.
- Model citation, complete response, and streaming event payloads.

## Non-responsibilities

No endpoint routing, authentication, conversation persistence, image decoding/storage, workflow execution, SSE formatting, or citation verification against retrieved evidence.

## Key types and functions

- `ResponseSource`: literal source values for prepared, figure-prepared, generated, out-of-domain, and clarification responses.
- `ConversationStatus`: `"active"` or `"ended"`.
- `ChatRequest`: optional conversation ID, required query, optional figure ID, and optional encoded image.
- `ChatRequest.validate_query`: trims and rejects all-whitespace input.
- `ChatRequest.validate_image`: trims input and validates either the whole string or the payload following a `data:image/...;base64,` prefix.
- `Citation`: citation ID plus a `KnowledgeSource`.
- `ChatResponse`: complete chat result with active default status and an independent empty citation list.
- `StreamingChatChunk`: start/chunk/end/error event with fields optional according to event use.

## Invariants and errors

- Conversation IDs are either absent or 1–255 characters; queries are initially 1–10,000 characters and remain nonblank after trimming.
- Figure IDs are at most 128 characters and image strings at most 10,000,000 characters.
- Invalid base64 raises a Pydantic validation error rooted in `ValueError("image must be a base64 image or data URL")`.
- Image validation checks encoding only; it does not verify decoded bytes are an actual image.
- Pydantic enforces all literal discriminator values and required response fields.

## Dependencies

- `pydantic` for models, fields, and validators.
- `KnowledgeSource` for citation provenance.
- Python `base64` and `binascii` for encoded-image validation.

## Tests

- `tests/test_api.py` verifies missing and blank queries, invalid image input, complete response shape, conversation defaults, and streaming event payloads through the API.
- Endpoint tests exercise these models indirectly rather than testing every field bound in isolation.

## Status

Implemented.
