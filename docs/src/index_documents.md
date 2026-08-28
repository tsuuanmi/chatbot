# `src/index_documents.py`

## Purpose

Builds the persistent knowledge and figure-description indexes used by the chatbot.

## Responsibilities

- Initialize the application container and knowledge indexer.
- Index `knowledge_base.tsv` first when it exists beneath the selected document directory.
- Index other supported documents in that directory.
- Optionally generate/reuse figure descriptions and index them in the figure store.
- Return and log the combined number of knowledge and figure records processed.
- Provide a script entry point that closes the LLM client and container even after failure.

## Non-responsibilities

No document chunking rules, TSV validation, figure asset discovery, description prompt definition, or vector-store implementation.

## Key types and functions

- `index_documents(directory=Path("data/documents"), *, index_figures=True) -> int`: asynchronously runs project indexing and returns the aggregate record count.
- `main() -> None`: runs default indexing and guarantees resource cleanup.

## Invariants and errors

- A missing `knowledge_base.tsv` is skipped, not treated as an error.
- Directory indexing always runs; figure indexing runs only when `index_figures` is true.
- Indexer, LLM, filesystem, and store errors propagate from `index_documents`.
- `main` closes the LLM client before the container in its `finally` block.

## Dependencies

- `src.container` for application resources.
- `KnowledgeIndexer` and `FigureDescriptionIndexer`.
- `FIGURE_DESCRIPTION_PROMPT`, `get_llm_client`, and `close_llm_client`.
- `asyncio`, `pathlib.Path`, and Loguru.

## Tests

`tests/test_indexing.py::test_project_indexer_includes_tsv_knowledge_base` verifies optional TSV detection, indexing, and returned count with figure indexing disabled. Other tests in that module cover the delegated knowledge and figure indexers.

## Status

Implemented.
