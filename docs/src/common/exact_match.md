# `src/common/exact_match.py`

## Purpose

Provides normalized exact-question lookup over approved prepared answers from the TSV knowledge base.

## Responsibilities

- Load knowledge entries and retain only records whose approval status is `approved`.
- Index each approved entry by its primary question and aliases.
- Normalize Unicode, case, punctuation, and whitespace consistently for indexing and lookup.
- Cache the process-default repository instance.
- Log whether approved prepared answers were loaded.

## Non-responsibilities

No fuzzy, semantic, substring, or ranked search; no approval mutation, TSV writing, cache invalidation, duplicate warning, or answer generation.

## Key types and functions

- `PreparedAnswerRepository(path=None)`: builds an in-memory normalized-key dictionary of approved entries.
- `find(question) -> KnowledgeEntry | None`: returns the exact normalized match.
- `_normalize(text)`: applies Unicode NFKC, case folding, punctuation replacement, and whitespace collapse.
- `get_prepared_answers()`: unbounded `lru_cache` factory for the default repository.

## Invariants and errors

- Only entries whose string status equals `ApprovalStatus.APPROVED` are indexed.
- Primary questions and aliases share one namespace; later dictionary-comprehension entries overwrite earlier normalized-key collisions without warning.
- Punctuation does not affect matching, while word characters are retained under Unicode rules.
- Knowledge-base parsing and file errors propagate from `load_knowledge_base`.

## Dependencies

- `KnowledgeEntry` and `load_knowledge_base` for source records.
- `ApprovalStatus` for the approved-status value.
- `loguru` for load outcome logging.
- Python `re`, `unicodedata`, `pathlib`, and `functools.lru_cache`.

## Tests

- `tests/test_answer.py::test_prepared_answer_repository_normalizes_approved_match` verifies approved loading, punctuation/case/whitespace normalization, and returned answer metadata.
- `tests/test_imports.py` verifies the module imports as an authoritative module.

## Status

Implemented.
