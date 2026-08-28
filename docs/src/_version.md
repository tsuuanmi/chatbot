# `src/_version.py`

## Purpose

Holds the single runtime source of truth for the application version string.

## Responsibilities

- Expose `__version__` for use by the FastAPI application metadata and the detailed
  health endpoint.

## Non-responsibilities

No dependency loading, no settings access, and no build-time packaging logic. The
  release packaging version is declared in `pyproject.toml`; this constant mirrors it
  for runtime reporting without requiring the package to be installed in the container.

## Key types and functions

- `__version__: str`: the application version, for example `"0.2.3"`.

## Invariants and errors

- The value must match the version in `pyproject.toml` so build metadata and runtime
  reporting agree.

## Dependencies

None.

## Tests

`tests/test_imports.py` imports the authoritative modules. Runtime version reporting is
  exercised through `tests/test_api.py` and `tests/test_integration.py`.

## Status

Implemented.