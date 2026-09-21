# Public API

The production public API is exposed only through Nginx.

Default local base URL:

```text
http://127.0.0.1:18080
```

The installer also prints the detected LAN URL.

## Authentication

`GET /live` is unauthenticated.

All other public application endpoints require:

```text
Authorization: Bearer <API_KEY>
```

The deployment user's API key is stored at:

```text
~/.local/share/chatbot/state/secrets/chat_api_key
```

## Liveness

```text
GET /live
```

Successful response:

```json
{"status":"ok"}
```

Authentication is not required.

## Readiness

```text
GET /ready
```

Requires Bearer authentication.

Use readiness to determine whether application dependencies are available.

Without authentication the endpoint returns `401 Unauthorized`.

## Chat

```text
POST /api/v1/chat
```

Request:

```json
{
  "query": "STR là gì?",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "figure_id": null,
  "image": null
}
```

`query` is required.

The public `/api/v1/chat` and `/api/v1/chat/stream` contract uses `query`, not `message`.

`conversation_id` is optional and must be a UUID. Omit it for a stateless request. For one-sitting conversational context, generate one UUID on the client and reuse it for consecutive turns.

`figure_id` and `image` are optional but mutually exclusive.

A configured `figure_id` refers only to an approved figure in the persistent figure store.

`image` accepts supported base64 image input. Raw image bytes are transient and are not persisted as conversation history.

Example response:

```json
{
  "answer": "STR là viết tắt của Short Tandem Repeats ...",
  "source": "generated",
  "decision": {
    "domain": "in_domain",
    "risk": "standard",
    "reason": "semantic_domain",
    "confidence": 0.54,
    "margin": 0.17,
    "risk_score": 0.30,
    "matched_rule": null
  },
  "evidence_status": "supporting",
  "citations": []
}
```

Stateful responses also include conversation metadata such as `conversation_id` and turn number.

## Streaming Chat

```text
POST /api/v1/chat/stream
```

Uses the same request fields as `/api/v1/chat` and returns Server-Sent Events.

The stream uses start, chunk, end, and error events. Conversation persistence occurs only after successful generation completion.

## Delete Conversation

```text
DELETE /api/v1/conversations/{conversation_id}
```

`conversation_id` must be a UUID. The authenticated identity determines conversation ownership; clients cannot provide a trusted owner ID.

## Example

```bash
API_KEY="$(cat "$HOME/.local/share/chatbot/state/secrets/chat_api_key")"

curl -sS \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"STR là gì?"}' \
  http://127.0.0.1:18080/api/v1/chat
```

The production gateway is intentionally not OpenAI-compatible. `/v1/models` and `/v1/chat/completions` are not public endpoints.

## Error Behavior

Common statuses:

- `401` — missing or invalid authentication
- `404` — endpoint is not publicly exposed
- `413` — request exceeds Nginx body limits
- `422` — invalid application request, UUID, image, figure, or mutually exclusive media inputs

## Public Boundary

Hayhooks/runtime-management endpoints are intentionally not public. The Nginx gateway does not expose endpoints such as `/chat/run`, `/chat/stream`, `/healthcheck/run`, `/status`, `/classify/run`, `/deploy-yaml`, `/deploy_files`, or `/undeploy/*`.

The supported client contract is the versioned `/api/v1` API documented here.
