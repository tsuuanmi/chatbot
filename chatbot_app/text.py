"""Small text-normalization helpers used by deterministic policy rules."""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9\s]")


def normalize_for_policy(text: str) -> str:
    """Normalize Vietnamese text for deterministic matching.

    This intentionally removes accents so the same policy also matches
    Vietnamese typed without diacritics.
    """

    text = text.strip().lower().replace("đ", "d")

    decomposed = unicodedata.normalize("NFD", text)

    text = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )

    text = _NON_WORD.sub(" ", text)
    text = _WHITESPACE.sub(" ", text)

    return text.strip()
