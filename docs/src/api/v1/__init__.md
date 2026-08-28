# `src/api/v1/__init__.py`

## Purpose

Aggregates the version 1 health and chat routes into one FastAPI router.

## Responsibilities

- Create the v1 `APIRouter`.
- Include the health router before the chat router.

## Non-responsibilities

No URL prefixing, authentication policy, or endpoint implementation. `src.api.app` mounts this router at `/api/v1`, and endpoint modules define their own dependencies.

## Key types and functions

- `router`: aggregate `APIRouter` containing routes from `health` and `chat`.

## Invariants and errors

Importing the module registers both child routers. It performs no I/O and defines no custom error handling.

## Dependencies

- FastAPI `APIRouter`.
- `src.api.v1.health` and `src.api.v1.chat`.

## Tests

`tests/test_imports.py` verifies that the aggregate route set includes chat, streaming chat, liveness, and readiness routes and excludes removed legacy routes.

## Status

Implemented.
