# `src/knowledge/citations.py`

## Purpose

Extracts, removes, and validates bracketed citation identifiers in generated answers.

## Responsibilities

- Parse citation-like tokens of the form `[identifier]` with no brackets or whitespace inside.
- Remove citations not present in the supplied evidence set.
- Reject answers containing citation IDs not backed by supplied evidence.

## Non-responsibilities

No citation insertion, answer generation, evidence retrieval, source formatting, or claim-level support analysis.

## Key types and functions

- `_CITATION_PATTERN`: regular expression for one non-whitespace bracket token.
- `citation_ids(answer)`: returns the distinct parsed IDs.
- `sanitize_citations(answer, evidence)`: preserves allowed tokens and removes unknown tokens.
- `validate_citations(answer, evidence)`: raises when any parsed ID is unknown.

## Invariants and errors

- Duplicate citations collapse in `citation_ids()` because it returns a set.
- Sanitization removes only the bracket token; surrounding spacing and prose are unchanged.
- Bracketed text containing whitespace is not considered a citation.
- `validate_citations()` raises `ValueError` with a sorted list of unknown IDs; it does not require any citation to be present.

## Dependencies

- Python `re`.
- `src.knowledge.models.Evidence` for allowed evidence IDs.

## Tests

`tests/test_knowledge.py` covers accepted evidence citations, rejection of unknown IDs, and sanitization of an invented citation.

## Status

Implemented.
