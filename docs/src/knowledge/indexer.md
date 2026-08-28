# `src/knowledge/indexer.py`

## Purpose

Indexes approved packaged knowledge and manifest-controlled PDF sources into a vector database.

## Responsibilities

- Load approved TSV knowledge entries, build searchable text/metadata, and replace that source atomically.
- Load and cross-validate all PDF manifests in a directory before mutating the database.
- Verify approved PDF files, extract page text, normalize and overlap chunks, and attach auditable provenance metadata.
- Replace each source, including replacing superseded or withdrawn sources with an empty record set.
- Enforce unique source IDs/files, reserve the packaged source ID, and reject unmanifested PDFs.

## Non-responsibilities

No manifest approval decisions, OCR, semantic retrieval, embedding implementation, citation validation, or incremental per-document merging.

## Key types and functions

- `_PACKAGED_SOURCE`: reserved identifier `knowledge_base.tsv`.
- `_PreparedSource`: immutable manifest plus prepared chunks and metadata.
- `KnowledgeIndexer.index_directory()`: validates and prepares the whole directory, then replaces every manifest source.
- `index_knowledge_base()`: indexes approved packaged TSV entries.
- `_prepare_directory()`: validates manifests/files and prepares approved PDF content.
- `_replace_source()`: delegates source replacement on a worker thread and returns record count.
- `_validate_manifests()`: enforces directory-wide identity and manifest coverage rules.
- `_read_pdf_chunks()`: extracts page chunks and provenance, stopping at `max_chunks`.
- `_chunk_text()`: whitespace-normalizes and yields overlapping chunks, preferring a space boundary.

## Invariants and errors

- Directory preparation completes before any source replacement, preventing partial writes for manifest or PDF validation failures.
- Only approved manifests are read; superseded and withdrawn sources are replaced with no records.
- Every PDF in the directory must have exactly one manifest; source IDs and referenced filenames must be unique.
- `knowledge_base.tsv` cannot be used as a PDF manifest source ID.
- Approved PDFs must exist, match their manifest hash, and contain extractable text.
- PDF parsing failures are wrapped as `ValueError("Invalid PDF source: ...")`; validation and vector-database errors otherwise propagate.
- Chunk normalization collapses all whitespace; default chunks target 1200 characters with 200-character overlap and always advance.
- PDF document IDs are stable one-based `pdf:<source_id>:chunk:<n>` values; packaged IDs are `knowledge:<entry number>`.

## Dependencies

- `BaseVectorDatabase.replace_source` for source-scoped replacement.
- `load_knowledge_base` for packaged TSV records.
- `SourceManifest`/`SourceStatus` and `ApprovalStatus` for controls.
- `pypdf.PdfReader` for PDF extraction, plus `asyncio`, `pathlib`, and Loguru.

## Tests

`tests/test_indexing.py` covers text chunking and packaged knowledge replacement. `tests/test_source_manifest.py` covers directory validation, rejected/unmanifested sources, empty approved PDFs, status-driven removal, preparation-before-write behavior, and PDF metadata/indexing paths. Importability is checked in `tests/test_imports.py`.

## Status

Implemented.
