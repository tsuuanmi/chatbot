# `src/knowledge/models.py`

## Purpose

Defines typed provenance and evidence records for approved knowledge retrieval.

## Responsibilities

- Represent the single retrievable approval state.
- Describe source identity and review-relevant provenance attached to evidence.
- Bundle retrieved content, distance, source, and arbitrary metadata.

## Non-responsibilities

No manifest validation, indexing, retrieval, ranking, or citation validation.

## Key types and functions

- `ApprovalStatus`: string enum containing `APPROVED`.
- `KnowledgeSource`: Pydantic source record with ID, title, authority, version, optional page/section, and approval status.
- `Evidence`: Pydantic retrieval record with ID, content, distance, source, and metadata.

## Invariants and errors

- Pydantic requires all non-default fields and validates the enum and declared field types.
- `page_or_section` defaults to an empty string.
- `metadata` accepts arbitrary value types, and `distance` has no range constraint in this model.

## Dependencies

- Python `StrEnum` and `typing.Any`.
- Pydantic `BaseModel`.

## Tests

`tests/test_knowledge.py` constructs source and evidence records for retrieval and citation checks. Other answer/workflow tests consume evidence-shaped state.

## Status

Implemented.
