# `src/figures/indexer.py`

## Purpose

Precomputes Vietnamese descriptions for configured scientific figures and synchronizes them with storage.

## Responsibilities

- Enumerate configured figures and load each asset without blocking the event loop.
- Reuse stored descriptions whose content hash still matches.
- Generate and trim descriptions for new or changed assets.
- Persist each generated description immediately with up to three focused storage retries.
- Log current/total progress while each figure is loaded, reused, generated, or stored.
- Remove records for figures no longer configured after all current figures are processed.
- Return and log the number of configured figures successfully indexed.

## Non-responsibilities

No image-model implementation, figure configuration parsing, vector-database implementation, or online chat response generation.

## Key types and functions

- `FIGURE_DESCRIPTION_PROMPT`: Vietnamese instructions requiring concise, evidence-bound scientific image analysis.
- `DescriptionGenerator`: asynchronous callable from `FigureAsset` to description text.
- `FigureDescriptionIndexer`: coordinates `FigureTool`, `FigureDescriptionStore`, and the generator.
- `index()`: performs one full synchronization pass and returns the configured figure count.

## Invariants and errors

- An unchanged content hash prevents regeneration.
- A configured figure that disappears during loading raises `RuntimeError`.
- A generated description must remain non-empty after stripping or `RuntimeError` is raised.
- A generated description is stored before the next figure is processed, so a later failure does not discard completed work.
- Storage failures are retried three times with five-second waits; exhaustion propagates the final exception.
- Generator and tool exceptions propagate immediately.

## Dependencies

- `FigureTool` and `FigureAsset` for configured asset access.
- `FigureDescriptionStore` and `FigureDescription` for persistence records.
- `asyncio.to_thread` for synchronous load/store calls and Loguru for reporting.

## Tests

`tests/test_indexing.py` covers reuse of matching hashes, generation for changed descriptions, persistence calls, and figure-store integration.

## Status

Implemented.
