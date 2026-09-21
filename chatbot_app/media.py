"""Safe validation for configured figure IDs and transient images."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass


DEFAULT_IMAGE_MAX_BYTES = 6 * 1024 * 1024

_FIGURE_ID_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9_-]{0,127}\Z"
)

_SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}


@dataclass(frozen=True, slots=True)
class ImageInput:
    """Validated transient image supplied by a client."""

    base64_image: str
    mime_type: str
    byte_size: int

    @property
    def data_url(self) -> str:
        return (
            f"data:{self.mime_type};base64,"
            f"{self.base64_image}"
        )


def normalize_figure_id(
    value: str | None,
) -> str | None:
    """Return one canonical safe figure identifier."""

    if value is None:
        return None

    figure_id = value.strip().lower()

    if not figure_id:
        raise ValueError(
            "figure_id must not be empty"
        )

    if not _FIGURE_ID_PATTERN.fullmatch(
        figure_id
    ):
        raise ValueError(
            "figure_id contains invalid characters"
        )

    return figure_id


def parse_image_input(
    value: str | None,
    *,
    max_bytes: int = DEFAULT_IMAGE_MAX_BYTES,
) -> ImageInput | None:
    """Validate raw base64 or a base64 image data URL."""

    if value is None:
        return None

    image = value.strip()

    if not image:
        raise ValueError(
            "image must not be empty"
        )

    declared_mime: str | None = None
    payload = image

    if image.lower().startswith("data:"):
        header, separator, payload = (
            image.partition(",")
        )

        if not separator:
            raise ValueError(
                "invalid image data URL"
            )

        header_parts = header.split(";")

        if (
            len(header_parts) != 2
            or header_parts[1].lower()
            != "base64"
        ):
            raise ValueError(
                "image data URL must use base64"
            )

        declared_mime = (
            header_parts[0]
            .removeprefix("data:")
            .lower()
        )

        if (
            declared_mime
            not in _SUPPORTED_MIME_TYPES
        ):
            raise ValueError(
                "unsupported image MIME type"
            )

    if not payload:
        raise ValueError(
            "image base64 payload is empty"
        )

    if max_bytes < 1:
        raise ValueError(
            "max_bytes must be positive"
        )

    max_encoded = (
        ((max_bytes + 2) // 3) * 4
    )

    if len(payload) > max_encoded:
        raise ValueError(
            "image exceeds maximum size"
        )

    try:
        raw = base64.b64decode(
            payload,
            validate=True,
        )
    except (
        binascii.Error,
        ValueError,
    ) as error:
        raise ValueError(
            "image must contain valid base64"
        ) from error

    if not raw:
        raise ValueError(
            "decoded image is empty"
        )

    if len(raw) > max_bytes:
        raise ValueError(
            "image exceeds maximum size"
        )

    detected_mime = _detect_mime_type(
        raw
    )

    if detected_mime is None:
        raise ValueError(
            "unsupported image format"
        )

    if (
        declared_mime is not None
        and declared_mime
        != detected_mime
    ):
        raise ValueError(
            "image MIME type does not match content"
        )

    return ImageInput(
        base64_image=payload,
        mime_type=detected_mime,
        byte_size=len(raw),
    )


def validate_media_input(
    *,
    figure_id: str | None = None,
    image: str | None = None,
    max_image_bytes: int = (
        DEFAULT_IMAGE_MAX_BYTES
    ),
) -> tuple[
    str | None,
    ImageInput | None,
]:
    """Validate mutually exclusive figure and image inputs."""

    normalized_figure = normalize_figure_id(
        figure_id
    )

    parsed_image = parse_image_input(
        image,
        max_bytes=max_image_bytes,
    )

    if (
        normalized_figure is not None
        and parsed_image is not None
    ):
        raise ValueError(
            "figure_id and image are mutually exclusive"
        )

    return (
        normalized_figure,
        parsed_image,
    )


def _detect_mime_type(
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
