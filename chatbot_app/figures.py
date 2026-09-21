"""Configured figure inventory and content identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from chatbot_app.media import (
    DEFAULT_IMAGE_MAX_BYTES,
    normalize_figure_id,
)


_SUPPORTED_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass(
    frozen=True,
    slots=True,
)
class FigureAsset:
    figure_id: str
    path: Path
    source_name: str
    content_hash: str
    mime_type: str
    byte_size: int


def scan_figures(
    directory: Path,
    *,
    max_bytes: int = DEFAULT_IMAGE_MAX_BYTES,
) -> list[FigureAsset]:
    """Return the validated canonical figure inventory."""

    if not directory.is_dir():
        raise RuntimeError(
            f"Figure directory not found: {directory}"
        )

    if max_bytes < 1:
        raise ValueError(
            "max_bytes must be positive"
        )

    assets: dict[
        str,
        FigureAsset,
    ] = {}

    for path in sorted(
        directory.iterdir()
    ):
        if not path.is_file():
            continue

        expected_mime = (
            _SUPPORTED_SUFFIXES.get(
                path.suffix.lower()
            )
        )

        if expected_mime is None:
            continue

        figure_id = normalize_figure_id(
            path.stem
        )

        assert figure_id is not None

        if figure_id in assets:
            raise RuntimeError(
                "Duplicate configured figure ID: "
                f"{figure_id}"
            )

        raw = path.read_bytes()

        if not raw:
            raise RuntimeError(
                f"Configured figure is empty: {path}"
            )

        if len(raw) > max_bytes:
            raise RuntimeError(
                "Configured figure exceeds maximum "
                f"size: {path}"
            )

        actual_mime = detect_image_mime(
            raw
        )

        if actual_mime is None:
            raise RuntimeError(
                "Configured figure has unsupported "
                f"content: {path}"
            )

        if actual_mime != expected_mime:
            raise RuntimeError(
                "Configured figure extension does "
                f"not match content: {path}"
            )

        assets[figure_id] = FigureAsset(
            figure_id=figure_id,
            path=path,
            source_name=path.name,
            content_hash=hashlib.sha256(
                raw
            ).hexdigest(),
            mime_type=actual_mime,
            byte_size=len(raw),
        )

    return list(
        assets.values()
    )


def detect_image_mime(
    raw: bytes,
) -> str | None:
    if raw.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return "image/png"

    if raw.startswith(
        b"\xff\xd8\xff"
    ):
        return "image/jpeg"

    if (
        len(raw) >= 12
        and raw[:4] == b"RIFF"
        and raw[8:12] == b"WEBP"
    ):
        return "image/webp"

    return None
