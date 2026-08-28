# `src/knowledge/__init__.py`

## Purpose

Defines the public interface for approved forensic-genetics knowledge handling.

## Responsibilities

- Re-export citation utilities, provenance models, manifest types, the indexer, and the retriever.

## Non-responsibilities

No indexing, retrieval, manifest validation, or citation processing at import time.

## Key types and functions

- `KnowledgeIndexer`, `KnowledgeRetriever`, `SourceManifest`, `KnowledgeSource`, `Evidence`, their status enums, and citation helpers.

## Invariants and errors

`__all__` enumerates the supported package exports. Import-time dependency errors propagate.

## Dependencies

- `src.knowledge.citations`, `indexer`, `manifest`, `models`, and `retriever`.

## Tests

Exports are exercised through knowledge, indexing, manifest, and import tests; no dedicated initializer tests.

## Status

Implemented.
