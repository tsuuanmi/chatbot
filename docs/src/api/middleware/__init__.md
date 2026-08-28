# `src/api/middleware/__init__.py`

## Purpose

Exposes the API error-handling middleware package interface.

## Responsibilities

- Re-export `ErrorHandlingMiddleware` and `add_error_handling`.

## Key types and functions

- `ErrorHandlingMiddleware`: middleware that converts application exceptions to JSON responses.
- `add_error_handling(app)`: installs that middleware on a FastAPI application.

## Invariants and errors

The module adds no behavior beyond importing and declaring its two public exports.

## Dependencies

- `src.api.middleware.error_handler`.

## Tests

No dedicated package-level tests; middleware installation is exercised through API tests using `create_app`.

## Status

Implemented.
