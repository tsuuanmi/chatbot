# `src/knowledge/retriever.py`

## Purpose

Retrieves chat evidence from approved knowledge records using combined semantic and lexical search.

## Responsibilities

- Run semantic and lexical searches concurrently without blocking the event loop.
- Merge duplicate hits by ID, retaining the lower-distance version.
- Rank by ascending distance and filter by configured distance and approval status.
- Convert metadata-backed hits into typed `Evidence` and `KnowledgeSource` records.
- Limit the final approved evidence list to `top_k`.

## Non-responsibilities

No indexing, embedding implementation, citation validation, reranking beyond distance, or answer generation.

## Key types and functions

- `KnowledgeRetriever.__init__()`: accepts a vector database, result limit, and maximum distance.
- `retrieve(query)`: returns approved, relevant evidence assembled from both search modes.

## Invariants and errors

- A hit is accepted only when `distance <= max_distance` and metadata approval equals `ApprovalStatus.APPROVED`.
- Duplicate IDs retain the hit with the smaller distance.
- Results are ordered by ascending distance and capped at `top_k`.
- Missing provenance fields become empty strings; source title falls back to source ID.
- Any exception from either search is logged and converted to an empty result list.
- Pydantic conversion errors occurring after search are not caught and propagate.

## Dependencies

- `BaseVectorDatabase` for similarity and lexical search.
- `ApprovalStatus`, `Evidence`, and `KnowledgeSource` for approval filtering and typed output.
- `asyncio` and Loguru.

## Tests

`tests/test_knowledge.py` covers combined approved retrieval and typed evidence used by citation validation. Importability is also checked in `tests/test_imports.py`.

## Status

Implemented.
