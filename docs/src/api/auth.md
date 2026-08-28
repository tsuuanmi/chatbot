# `src/api/auth.py`

## Purpose

Authenticates trusted LAN API clients with bearer keys stored only as SHA-256 hashes.

## Responsibilities

- Hash plaintext API keys with SHA-256.
- Strictly load version 1 JSON client records from the configured key file.
- Validate client identifiers, lowercase hexadecimal token hashes, uniqueness, and nonempty configuration.
- Compare a presented bearer token against every configured hash with constant-time comparison.
- Return a stable authenticated client identity or a development identity when authentication is disabled.

## Non-responsibilities

No key generation, key-file mutation, token caching, authorization beyond client identity, or TLS enforcement.

## Key types and functions

- `AuthenticatedClient`: frozen, slotted dataclass containing `client_id`.
- `hash_api_key(api_key) -> str`: returns the lowercase SHA-256 hex digest.
- `_load_key_hashes(path) -> dict[str, str]`: validates and returns client ID-to-hash mappings.
- `healthcheck_authentication()`: validate the key file at startup when auth is enabled.
- `require_client(credentials) -> AuthenticatedClient`: FastAPI security dependency for bearer authentication.

## Invariants and errors

- Client IDs are 2–64 characters and use only letters, digits, `.`, `_`, and `-`, beginning with an alphanumeric character.
- Stored hashes must be exactly 64 hexadecimal characters; they are case-folded before validation.
- Malformed, missing, duplicate, empty, or unreadable key configuration becomes `RuntimeError` internally and HTTP 503 at the API boundary.
- Missing, non-bearer, or unmatched credentials return HTTP 401 with `WWW-Authenticate: Bearer`.
- Plaintext credentials are hashed for comparison and are not stored in `AuthenticatedClient`.

## Dependencies

- Python hashing, JSON, regular expressions, secrets, dataclasses, and paths.
- FastAPI security and HTTP exception APIs.
- `src.config.settings.get_settings` and Loguru.

## Tests

`tests/test_api.py` verifies successful configured-client authentication, rejection
of a wrong key with 401, and missing or malformed key configuration with 503. API
fixtures exercise authentication-disabled local development.

## Status

Implemented.
