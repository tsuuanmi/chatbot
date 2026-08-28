# `src/domain/__init__.py`

## Purpose

Defines the public interface for semantic domain routing.

## Responsibilities

- Re-export the classifier and its decision enums/model.

## Non-responsibilities

No classification execution or model validation beyond imported definitions.

## Key types and functions

- `DomainClassifier`, `DomainDecision`, `DomainLabel`, `DomainReason`, and `RiskLevel`.

## Invariants and errors

`__all__` enumerates the five supported package exports. Import-time dependency errors propagate.

## Dependencies

- `src.domain.classifier` and `src.domain.models`.

## Tests

Exports are exercised indirectly by classifier and workflow tests; no dedicated initializer tests.

## Status

Implemented.
