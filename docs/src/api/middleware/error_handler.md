# `src/api/middleware/error_handler.py`

## Purpose

Provides consistent JSON responses and logging for exceptions that escape API request handlers.

## Responsibilities

- Pass requests to the next ASGI handler.
- Map known `FrameworkError` subclasses through `HTTP_STATUS_CODES` and expose their class name and message.
- Log and convert any other exception to a generic HTTP 500 response without exposing internal details.
- Install the middleware on a FastAPI application.

## Non-responsibilities

No request validation, authentication, route-specific `HTTPException` handling, or retry policy.

## Key types and functions

- `ErrorHandlingMiddleware.dispatch(request, call_next) -> Response`: executes a request and converts escaped exceptions to `JSONResponse` objects.
- `add_error_handling(app) -> None`: adds `ErrorHandlingMiddleware` to the application.

## Invariants and errors

- Known framework errors use the configured status or 500 when their type is absent from the mapping.
- Unknown errors return type `InternalServerError` and message `An unexpected error occurred`.
- Exceptions are logged; handled exceptions do not propagate beyond the middleware.

## Dependencies

- FastAPI and Starlette request, response, application, and middleware APIs.
- Loguru for error logging.
- `src.common.exceptions` for `FrameworkError` and `HTTP_STATUS_CODES`.

## Tests

No dedicated middleware unit tests. `tests/test_api.py` exercises application responses with the middleware installed by `create_app`.

## Status

Implemented.
