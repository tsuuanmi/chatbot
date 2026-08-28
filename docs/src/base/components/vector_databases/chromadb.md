# `src/base/components/vector_databases/chromadb.py`

## Purpose

Implements the vector-database contract against a remote ChromaDB server over its HTTP client.

## Responsibilities

- Configure a ChromaDB HTTP client from project settings and lazily get or create the named collection.
- Replace all records for one metadata `source`, or upsert records by deleting and re-adding their IDs.
- Embed document batches before adding them and embed queries for semantic search.
- Convert ChromaDB results into `SearchHit` records.
- Provide exact-ID lookup, ID listing, local lexical-overlap search, and deletion.

## Non-responsibilities

No ChromaDB server lifecycle, retries, authentication, schema migration, transaction rollback, embedding caching, stemming, phrase search, or pagination.

## Key types and functions

- `ChromaVectorDatabase(embedding, collection_name="default")`: configures the remote client.
- `_collection()`: gets or creates the configured collection.
- `replace_source(source, ids, texts, metadatas)`: deletes records matching `source`, then adds the replacement batch when non-empty.
- `upsert(ids, texts, metadatas)`: deletes matching IDs and adds the supplied batch; empty IDs are a no-op.
- `get_by_id(document_id)`: returns an exact hit with distance `0.0`, or `None`.
- `similarity_search(query, k=5)`: queries by embedding and returns Chroma distances.
- `lexical_search(query, k=5)`: ranks all documents by the fraction of query terms present.
- `_add(...)`: embeds texts and calls `Collection.add`.

## Invariants and errors

- IDs, texts, and metadata must have equal lengths for replacement and upsert; mismatches raise `ValueError`.
- Query result ID, document, metadata, and distance sequences must align; strict `zip` raises `ValueError` if their lengths differ.
- Lexical tokens are Unicode word sequences of at least two characters; a query with no such terms returns no hits.
- Backend, settings, and embedding failures propagate. Replacement deletes existing source records before embedding/addition, so a later failure is not rolled back.

## Dependencies

- `chromadb` and its `Collection`/`Metadata` types for remote storage.
- `BaseEmbedding`, `BaseVectorDatabase`, and `SearchHit` for component boundaries.
- `get_settings` for Chroma host and port.
- `loguru` for client-configuration logging.
- Python `re` for lexical tokenization.

## Tests

No direct ChromaDB-backed test currently exists. `tests/test_knowledge.py` and `tests/test_indexing.py` test consumers through mocked `BaseVectorDatabase` behavior.

## Status

Implemented.
