"""Absolute semantic relevance policy for RAG evidence."""

from __future__ import annotations

import math
import os


DEFAULT_MIN_SEMANTIC_SCORE = 0.68


def minimum_semantic_score() -> float:
    raw = os.environ.get(
        "RAG_MIN_SEMANTIC_SCORE",
        str(DEFAULT_MIN_SEMANTIC_SCORE),
    )

    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(
            "RAG_MIN_SEMANTIC_SCORE must be numeric"
        ) from error

    if (
        not math.isfinite(value)
        or value < 0.0
        or value > 1.0
    ):
        raise RuntimeError(
            "RAG_MIN_SEMANTIC_SCORE must be between 0 and 1"
        )

    return value


def is_semantically_relevant(
    score: float | None,
    minimum: float,
) -> bool:
    if score is None:
        return False

    return score >= minimum
