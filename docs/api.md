# API Reference

Offline LAN base URL: `http://<target-ip>/api/v1`

This offline profile is unencrypted and must be restricted to an isolated, trusted
LAN. Except for liveness, offline endpoints require `Authorization: Bearer <client-api-key>`.
The development Compose path may explicitly disable authentication. Conversations
are owned by the authenticated client; another API key cannot continue or delete
them. The application does not expose expert switching. `GET /health` is retained
only as a compatibility liveness alias. `query` is the sole chat input field.
Streaming endpoints use one JSON Server-Sent Events format.

## Liveness and Readiness

### `GET /live` and compatibility alias `GET /health`

Public process liveness only:

```json
{"status":"healthy"}
```

### `GET /ready`

Requires an API key. Functionally verifies PostgreSQL, ChromaDB, EmbeddingGemma,
Gemma, classifier warmup, and required indexes. Returns HTTP 503 until all checks
are ready.

### `GET /health/detailed`

Requires an API key. Returns configured LLM and embedding model names for operator
diagnostics.

## Chat

### `POST /chat`

Request:

```json
{
  "conversation_id": "optional-client-id",
  "query": "Giải thích STR",
  "figure_id": "optional-safe-figure-id",
  "image": "optional-base64-or-data-image-url"
}
```

If `conversation_id` is omitted, the server generates a UUID. Each ID is scoped to
the authenticated client. `image` does not accept filesystem paths.

Response:

```json
{
  "response": "...",
  "conversation_id": "optional-client-id",
  "source": "generated",
  "conversation_status": "active",
  "citations": [
    {
      "id": "knowledge:25",
      "source": {
        "id": "internal-figure-faq",
        "title": "Bộ câu hỏi đáp hình minh họa giám định ADN",
        "authority": "BCA - nội dung dự án",
        "version": "1.0",
        "page_or_section": "pie1",
        "approval_status": "approved"
      }
    }
  ]
}
```

`source` is one of:

- `prepared_answer`: normalized approved match from `knowledge_base.tsv`; no LLM call
- `figure_prepared`: stored precomputed description for a configured figure; no image encode or LLM call
- `generated`: Gemma-generated answer for an in-domain question (with or without RAG context)
- `out_of_domain`: semantic classification rejected the question; no full history, retrieval, or Gemma generation is performed and status is `ended`
- `clarification`: semantic classification needs bounded context before the request can be accepted; status remains `active`

`citations` contains only approved source records whose `[ID]` was actually emitted in
the answer. It is empty for direct, clarification, out-of-domain, and ungrounded answers.

### `POST /chat/stream`

Uses the same request. Response media type is `text/event-stream`; every event is a JSON object in a `data:` line.

```text
data: {"type":"start","conversation_id":"id","source":"generated"}

data: {"type":"chunk","conversation_id":"id","content":"token","source":"generated"}

data: {"type":"end","conversation_id":"id","source":"generated","conversation_status":"active","citations":[]}
```

On stream failure:

```text
data: {"type":"error","conversation_id":"id","source":"generated","error":"An unexpected error occurred","conversation_status":"active"}
```

### `DELETE /conversations/{conversation_id}`

```json
{"status":"success","deleted_turns":2}
```

## Knowledge Ingestion

Knowledge ingestion is not exposed through the public API. Controlled project TSV/PDF
sources are reviewed and indexed by an operator with `make index` online or
`make index MODE=offline` on an installed target. This prevents arbitrary uploads
from entering the approved evidence collection.

## Validation and Errors

Missing/invalid API keys return HTTP 401. Capacity saturation returns HTTP 429
with `Retry-After`. FastAPI validation errors return HTTP 422. Readiness or semantic
classifier unavailability returns HTTP 503. Unexpected errors are sanitized:

```json
{
  "error": {
    "type": "InternalServerError",
    "message": "An unexpected error occurred"
  }
}
```

## Removed APIs

These obsolete paths intentionally no longer exist:

- `/experts/*`
- `POST /clear/{conversation_id}`
- `/rag/*` (public upload/query bypass removed)
- `input` as an alias for `query`
- `additional_kwargs` response metadata
