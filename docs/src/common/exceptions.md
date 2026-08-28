# `src/common/exceptions.py`

## Purpose

Defines the framework exception hierarchy and its HTTP status mapping.

## Responsibilities

- Provide one base exception carrying a public `message` attribute.
- Distinguish LLM-client, memory, configuration, and domain-classification failures by type.
- Map known framework exception classes to service-level HTTP status codes.

## Non-responsibilities

No exception handling, logging, response serialization, retry policy, or error-code payload generation.

## Key types and functions

- `FrameworkError`: base exception; defaults to `"An error occurred in the framework"`.
- `LLMClientError`: LLM service failure, mapped to HTTP 503.
- `MemoryError`: application memory-layer failure, mapped to HTTP 500; this name is distinct from but shadows Python's built-in name within this module.
- `ConfigurationError`: configuration failure, mapped to HTTP 500.
- `DomainClassifierError`: classifier failure, mapped to HTTP 503.
- `HTTP_STATUS_CODES`: exact-class-to-status dictionary, including `FrameworkError` at 500.

## Invariants and errors

All specialized exceptions inherit `FrameworkError` unchanged. The status mapping is keyed by exact classes; callers using `HTTP_STATUS_CODES.get(type(error), 500)` do not perform subclass fallback beyond explicitly listed types.

## Dependencies

Only Python's built-in `Exception`.

## Tests

- `tests/test_domain_classifier.py` verifies classifier failures raise `DomainClassifierError` with the expected message.
- API error middleware consumes `FrameworkError` and `HTTP_STATUS_CODES`; no direct mapping test currently exists.

## Status

Implemented.
