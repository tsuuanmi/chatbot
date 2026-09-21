"""Deterministic routing for configured figure requests."""

from __future__ import annotations

import re


_ANALYSIS_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"mô\s+tả|miêu\s+tả|giải\s+thích|phân\s+tích|"
    r"describe|explain|analy[sz]e"
    r")(?!\w)",
    re.IGNORECASE,
)

_SPECIFIC_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"tại\s+sao|vì\s+sao|bao\s+nhiêu|so\s+sánh|"
    r"why|how\s+many|compare"
    r")(?!\w)",
    re.IGNORECASE,
)


def is_direct_figure_request(
    query: str,
) -> bool:
    normalized = " ".join(
        query.split()
    )

    return bool(
        _ANALYSIS_PATTERN.search(
            normalized
        )
        and not _SPECIFIC_PATTERN.search(
            normalized
        )
    )
