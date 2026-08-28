# `src/container.py`

## Purpose

Owns construction, process-wide reuse, and shutdown of the application's local dependency graph.

## Responsibilities

- Define the immutable `ApplicationContainer` carrying settings, embedding, stores, tools, classifier, and retriever.
- Lazily build a singleton container from validated settings.
- Create separate knowledge and figure vector databases backed by the same embedding component.
- Configure domain-classification and retrieval thresholds from settings.
- Close the owned embedding resource and clear the singleton during shutdown.

## Non-responsibilities

No HTTP dependency injection, database-history lifecycle, LLM-client shutdown, indexing, or request processing.

## Key types and functions

- `ApplicationContainer`: frozen, slotted dataclass containing all constructed application dependencies.
- `ApplicationContainer.close() -> None`: closes the embedding component.
- `setup_container() -> ApplicationContainer`: constructs the singleton on first use and returns it.
- `get_container() -> ApplicationContainer`: delegates to `setup_container`.
- `close_container() -> None`: closes and clears an existing singleton; otherwise does nothing.

## Invariants and errors

- At most one container is retained in `_container` per process.
- Both vector databases share one embedding instance but use distinct configured collection names.
- Construction failures propagate and do not assign a partially built container.
- `close_container` resets `_container` only after `ApplicationContainer.close` returns; an embedding close error propagates.

## Dependencies

- Embedding and vector-database factories from `src.base.components`.
- `Settings`/`get_settings`.
- `DomainClassifier`, `FigureDescriptionStore`, `KnowledgeRetriever`, and `FigureTool`.
- Loguru for initialization logging.

## Tests

No dedicated container unit tests. `tests/conftest.py` replaces setup and shutdown in API lifecycle tests, while workflow and indexing tests inject container-shaped mocks.

## Status

Implemented.
