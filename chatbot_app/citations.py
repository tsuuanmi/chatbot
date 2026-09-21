"""Explicit citation IDs and post-generation citation validation."""

from __future__ import annotations

import re
from typing import Mapping


_CITATION_PATTERN = re.compile(
    r"\[cite:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]"
)


def citation_id_from_meta(
    meta: Mapping[str, object],
    *,
    fallback_id: str,
) -> str:
    source_id = str(meta.get("source_id") or "").strip()
    number = str(meta.get("no") or "").strip()

    if source_id and number:
        raw = f"{source_id}:{number}"
    else:
        raw = fallback_id[:24]

    return re.sub(
        r"[^A-Za-z0-9._:-]+",
        "-",
        raw,
    ).strip("-")


def citation_token(citation_id: str) -> str:
    return f"[cite:{citation_id}]"


def citation_ids(text: str) -> set[str]:
    return set(_CITATION_PATTERN.findall(text))


def sanitize_citations(
    text: str,
    allowed: set[str],
) -> str:
    """Remove only unknown explicit citations.

    Ordinary brackets such as [1] or [DNA] are untouched.
    """

    return _CITATION_PATTERN.sub(
        lambda match: (
            match.group(0)
            if match.group(1) in allowed
            else ""
        ),
        text,
    )


class CitationStreamFilter:
    """Validate explicit citation tokens while text is streamed."""

    _MARKER = "[cite:"
    _MAX_TOKEN_LENGTH = 135

    def __init__(
        self,
        allowed: set[str],
    ) -> None:
        self.allowed = allowed
        self._buffer = ""

    def feed(
        self,
        text: str,
    ) -> str:
        if not text:
            return ""

        self._buffer += text
        output: list[str] = []

        while self._buffer:
            start = self._buffer.find(
                self._MARKER
            )

            if start < 0:
                retain = self._partial_marker_suffix(
                    self._buffer
                )

                if retain:
                    output.append(
                        self._buffer[:-retain]
                    )
                    self._buffer = (
                        self._buffer[-retain:]
                    )
                else:
                    output.append(
                        self._buffer
                    )
                    self._buffer = ""

                break

            if start > 0:
                output.append(
                    self._buffer[:start]
                )
                self._buffer = (
                    self._buffer[start:]
                )

            end = self._buffer.find("]")

            if end < 0:
                if (
                    len(self._buffer)
                    > self._MAX_TOKEN_LENGTH
                ):
                    output.append(
                        self._buffer[0]
                    )
                    self._buffer = (
                        self._buffer[1:]
                    )
                    continue

                break

            candidate = self._buffer[
                : end + 1
            ]

            match = _CITATION_PATTERN.fullmatch(
                candidate
            )

            if (
                match is None
                or match.group(1)
                in self.allowed
            ):
                output.append(candidate)

            self._buffer = self._buffer[
                end + 1 :
            ]

        return "".join(output)

    def finish(self) -> str:
        tail = sanitize_citations(
            self._buffer,
            self.allowed,
        )
        self._buffer = ""
        return tail

    @classmethod
    def _partial_marker_suffix(
        cls,
        value: str,
    ) -> int:
        maximum = min(
            len(value),
            len(cls._MARKER) - 1,
        )

        for size in range(
            maximum,
            0,
            -1,
        ):
            if value.endswith(
                cls._MARKER[:size]
            ):
                return size

        return 0
