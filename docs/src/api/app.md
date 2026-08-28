# `src/api/app.py`

## Purpose

Constructs the FastAPI application and owns startup and shutdown sequencing for shared resources.

## Responsibilities

- Define the application lifespan around container, history database, LLM-client, and readiness operations.
- Connect history storage and complete dependency warmup before serving requests.
- Close history, the LLM client, and the dependency container during shutdown, including after startup or serving failures.
- Configure API metadata and conditionally expose OpenAPI, Swagger UI, and ReDoc.
- Install restricted CORS, error middleware, and the v1 router at `/api/v1`.

## Non-responsibilities

No endpoint implementation, settings validation, authentication, workflow execution, or dependency construction details.

## Key types and functions

- `lifespan(app) -> AsyncGenerator[None, None]`: async context manager for startup and shutdown.
- `create_app() -> FastAPI`: returns a configured application instance.

## Invariants and errors

- Requests are not accepted through a completed startup until history connects and warmup succeeds.
- Shutdown runs from `finally`; history closes before the LLM client and container.
- API documentation routes are all enabled or all disabled by `api_docs_enabled`.
- CORS permits configured origins, no credentials, only `GET`, `POST`, `DELETE`, and `OPTIONS`, and only content-type and authorization headers.
- Startup and shutdown errors propagate after the applicable cleanup attempts.

## Dependencies

- FastAPI, its CORS middleware, and `asynccontextmanager`.
- API v1 router and error middleware.
- Settings, container, history service, LLM-client cleanup, readiness warmup, and Loguru.

## Tests

`tests/conftest.py` exercises the lifespan with resources patched in API fixtures. `tests/test_api.py` covers mounted endpoint contracts, and `tests/test_imports.py` verifies the authoritative route set.

## Status

Implemented.
