# `src/common/knowledge_base.py`

## Purpose

Provides typed, read-only loading of the project's tab-separated question-and-answer knowledge base.

## Responsibilities

- Represent a knowledge row and its provenance as an immutable `KnowledgeEntry`.
- Resolve the packaged default TSV path.
- Read UTF-8 tab-separated rows, skip rows without a term or description, normalize optional fields, and preserve valid entries in file order.

## Non-responsibilities

No approval filtering, semantic validation of provenance, duplicate detection, indexing, searching, writing, logging, or cache management.

## Key types and functions

- `KnowledgeEntry`: frozen, slotted dataclass for question, answer, aliases, topic, optional figure, provenance, review fields, and approval status.
- `default_knowledge_base_path()`: resolves `<repository>/data/documents/knowledge_base.tsv` from this module's location.
- `load_knowledge_base(path=None)`: loads the explicit or default TSV into `KnowledgeEntry` values.

## Invariants and errors

- A missing or non-file path returns an empty list.
- Rows lacking a nonblank `term` or `description` are silently skipped.
- Aliases are split on `|`, trimmed, and empty aliases removed; most optional columns become empty strings, `figure_id` becomes `None`, and absent approval status becomes `"draft"`.
- `number` is parsed from `no`, falling back to the one-based data-row index. Invalid non-empty numeric text raises `ValueError`.
- File decoding and I/O errors other than a missing/non-file path propagate.

## Dependencies

- Python `csv.DictReader` for TSV parsing.
- `dataclasses` for immutable entries.
- `pathlib.Path` for path resolution and file access.

## Tests

- `tests/test_answer.py` exercises loading through `PreparedAnswerRepository`, including approved entry fields.
- `tests/test_indexing.py` exercises explicit-path loading through `KnowledgeIndexer` and project indexing.

## Status

Implemented.
