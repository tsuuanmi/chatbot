# `src/tools/figure_tool.py`

## Purpose

Loads configured image files into bounded, normalized assets without accepting arbitrary path syntax from callers.

## Responsibilities

- Resolve figure files only beneath the configured figures directory and only for supported extensions.
- Validate figure identifiers against an ASCII letter, digit, underscore, and hyphen allowlist.
- Load and convert source images to RGB, resize them within a maximum bounding box, and encode them as PNG.
- Preserve a SHA-256 hash of the original source bytes for change detection.
- List supported figure stems in deterministic sorted order.

## Non-responsibilities

No figure description generation, vector indexing, semantic lookup, HTTP serving, cache management, or authorization. It does not recursively scan subdirectories.

## Key types and functions

- `_ALLOWED_EXTENSIONS`: supported source suffixes: PNG, JPG/JPEG, and WebP.
- `FigureAsset`: immutable slotted dataclass containing canonical stem, source hash, base64 PNG data, MIME type, and output dimensions.
- `FigureTool(figures_dir=None)`: resolves an explicit directory or the configured default.
- `FigureTool.load(figure_id, max_size=(1024, 1024)) -> FigureAsset | None`: finds, decodes, normalizes, thumbnails, and packages one figure.
- `FigureTool.list_figures() -> list[str]`: returns sorted stems for supported files in the configured directory.
- `FigureTool._find_file(figure_id) -> Path | None`: strips an optional supported suffix, validates the stem, and searches extensions in fixed precedence order.

## Invariants and errors

- IDs containing separators, dots outside one recognized suffix, whitespace, or other non-allowlisted characters return no asset.
- Missing files and missing figure directories return `None` or an empty list rather than raising.
- Output is always RGB PNG with MIME type `image/png`; resizing preserves aspect ratio and does not enlarge images beyond Pillow's thumbnail behavior.
- `content_hash` describes original bytes, not the normalized PNG.
- File read errors, invalid image data, Pillow decoding/encoding errors, and invalid `max_size` values propagate to the caller.
- If several supported files share a stem, `_ALLOWED_EXTENSIONS` order determines which one is loaded.

## Dependencies

- `Pillow` for image decoding, RGB conversion, thumbnailing, and PNG encoding.
- `src.config.settings.get_settings` for the default figures directory.
- Standard-library base64, hashing, regular expressions, byte streams, dataclasses, and paths.
- Loguru for initialization logging.

## Tests

`tests/test_indexing.py::test_figure_indexer_reuses_unchanged_descriptions` verifies loading and stable source hashes. `test_figure_indexer_generates_changed_descriptions` exercises listing/loading integration and confirms changed content produces a different hash. Identifier rejection and image-error paths have no dedicated tests.

## Status

Implemented.
