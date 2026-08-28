# `src/config/settings.py`

## Purpose

Defines and caches environment-backed application configuration for models, storage, retrieval, startup, and HTTP serving.

## Responsibilities

- Load settings through Pydantic from environment variables and `.env` or `/app/.env`.
- Require connection details and names for the LLM, embedding service, database, and primary Chroma collection.
- Provide bounded defaults for generation, classification, retrieval, startup retry, and API capacity controls.
- Parse comma-separated CORS origins into a trimmed list.
- Cache one `Settings` instance per process.

## Non-responsibilities

No connectivity checks, secret-file parsing, resource construction, or cross-field validation.

## Key types and functions

- `Settings`: `BaseSettings` model containing all application configuration fields.
- `Settings.allowed_origins -> list[str]`: splits `cors_origins`, trims entries, and removes empty entries.
- `get_settings() -> Settings`: constructs and memoizes settings with `lru_cache`.

## Invariants and errors

- Unknown environment or dotenv fields are ignored.
- Pydantic enforces declared numeric bounds: figure description tokens, domain thresholds, RAG limits, history depth, startup retries/delay, concurrency, and a queue timeout of at most 900 seconds.
- `llama_base_url`, `llama_api_key`, `llama_model_name`, embedding connection/name fields, `database_url`, and `chroma_collection_name` have no defaults and must be supplied.
- `allowed_origins` may be empty when `cors_origins` contains only separators or whitespace; origins are not otherwise normalized or validated here.
- Missing required values or invalid field values raise Pydantic settings validation errors when the cached instance is first created.

## Dependencies

- `pydantic.Field`, `pydantic_settings.BaseSettings`, and `SettingsConfigDict`.
- `functools.lru_cache`.

## Tests

No dedicated settings-model tests. API authentication and capacity tests patch `get_settings`; application and integration tests exercise configuration indirectly.

## Status

Implemented.
