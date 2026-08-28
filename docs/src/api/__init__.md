# `src/api/__init__.py`

## Purpose

Defines the public entry point for constructing the FastAPI application.

## Responsibilities

- Re-export `create_app` from `src.api.app`.
- Limit the declared public API to `create_app` through `__all__`.

## Non-responsibilities

No route registration, middleware setup, or resource lifecycle management; those remain in the imported API modules.

## Key types and functions

- `create_app() -> FastAPI`: re-exported application factory.

## Invariants and errors

Importing this package imports `src.api.app`; configuration and resources are not initialized until the factory or application lifespan runs.

## Dependencies

- `src.api.app` for `create_app`.

## Tests

`tests/test_imports.py` imports the application factory and verifies the authoritative route set.

## Status

Implemented.
