# `src/api/v1/health.py`

## Purpose

Exposes process liveness, dependency readiness, and authenticated model metadata endpoints.

## Responsibilities

- Serve unauthenticated liveness aliases at `/live` and `/health`.
- Run the full readiness check at `/ready`, protect it with client authentication, and return HTTP 503 when not ready.
- Serve an authenticated `/health/detailed` response with configured model names and API version.

## Non-responsibilities

No dependency warmup, readiness-check implementation, application-level `/api/v1` prefixing, or model health verification inside the detailed metadata endpoint.

## Key types and functions

- `liveness() -> dict[str, str]`: returns `{"status": "healthy"}` when the process can serve the request.
- `readiness(response, client) -> dict`: returns aggregate status plus per-dependency checks and mutates the response status to 503 when needed.
- `detailed_health_check(client) -> dict[str, str]`: returns static health status, configured LLM and embedding model names, and version `1.0.0`.
- `router`: health-tagged `APIRouter`.

## Invariants and errors

- Liveness does not inspect dependencies and requires no bearer client.
- Readiness and detailed health require `require_client`.
- Readiness returns `status` as `ready` or `not_ready`; detailed health always reports `healthy` if its handler executes.
- Authentication and dependency errors follow their FastAPI or middleware error paths.

## Dependencies

- FastAPI routing, dependency injection, response, and status APIs.
- API authentication, settings, application container, history service, and `check_readiness`.

## Tests

`tests/test_api.py::test_health` covers the liveness alias. `tests/test_imports.py` verifies `/live` and `/ready` registration. `tests/test_integration.py` calls the detailed health endpoint in the deployed service.

## Status

Implemented.
