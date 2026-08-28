# `src/knowledge/manifest.py`

## Purpose

Validates auditable release manifests and source files for controlled PDF knowledge ingestion.

## Responsibilities

- Define source lifecycle and access classifications.
- Strictly validate manifest structure, identifiers, PDF filenames, hashes, review separation, and release dates.
- Load a JSON manifest from disk into a typed model.
- Verify that the referenced PDF exists and matches its declared SHA-256 digest.

## Non-responsibilities

No PDF text extraction, chunking, indexing, retrieval, or approval workflow execution.

## Key types and functions

- `SourceStatus`: `approved`, `superseded`, or `withdrawn`.
- `AccessClass`: currently only `internal`.
- `SourceManifest`: extra-forbidding Pydantic model for one controlled source version.
- `validate_source_id()`, `validate_file()`, and `validate_hash()`: normalize or reject identity fields.
- `validate_release()`: enforces reviewer/approver and date rules.
- `load(path)`: reads JSON and validates it.
- `verify_file(directory)`: verifies file presence and SHA-256, then returns its path.

## Invariants and errors

- Extra manifest fields are forbidden.
- `source_id` is 3–128 lowercase characters from the allowed identifier alphabet.
- `file` must be one basename ending in `.pdf`, with no path component.
- SHA-256 is normalized to lowercase and must contain exactly 64 hexadecimal characters.
- Reviewer and approver must differ case-insensitively; review dates cannot be future dates.
- Approved sources cannot have a future effective date; non-approved sources may.
- `max_chunks` is between 1 and 1000, inclusive.
- Invalid JSON/read operations, invalid fields, missing PDFs, and hash mismatches surface as `ValueError`.

## Dependencies

- Pydantic validators and constrained fields.
- Standard-library hashing, JSON, regular expressions, dates, and paths.

## Tests

`tests/test_source_manifest.py` covers strict fields, path and hash validation, reviewer/approver separation, date rules, file verification, and use during controlled directory indexing.

## Status

Implemented.
