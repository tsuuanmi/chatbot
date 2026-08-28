# `src/domain/models.py`

## Purpose

Defines the typed vocabulary returned by semantic domain routing.

## Responsibilities

- Represent routing labels, risk levels, decision reasons, and complete classifier decisions.

## Non-responsibilities

No embedding, scoring, thresholding, persistence, or response policy.

## Key types and functions

- `DomainLabel`: `IN_DOMAIN`, `OUT_OF_DOMAIN`, or `CLARIFY`.
- `RiskLevel`: `STANDARD` or `HIGH_RISK`.
- `DomainReason`: enumerates forensic scope, configured figures, contextual follow-ups, unrelated topics, ambiguity, and case-specific conclusions.
- `DomainDecision`: Pydantic model with `label`, `risk`, `reason`, and floating-point `confidence`.

## Invariants and errors

- Enum values are stable strings suitable for serialization and persistence.
- Pydantic requires all four `DomainDecision` fields and validates enum membership and field types.
- The model itself does not constrain confidence to a numeric interval.

## Dependencies

- Python `StrEnum`.
- Pydantic `BaseModel`.

## Tests

Used throughout `tests/test_domain_classifier.py`, `tests/test_answer.py`, `tests/test_workflow.py`, `tests/test_postgres.py`, and API tests. No standalone model-only test file.

## Status

Implemented.
