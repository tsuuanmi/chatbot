"""Citation extraction and validation."""

import re

from src.knowledge.models import Evidence

_CITATION_PATTERN = re.compile(r"\[([^\[\]\s]+)\]")


def citation_ids(answer: str) -> set[str]:
    return set(_CITATION_PATTERN.findall(answer))


def sanitize_citations(answer: str, evidence: list[Evidence]) -> str:
    allowed = {item.id for item in evidence}
    return _CITATION_PATTERN.sub(
        lambda match: match.group(0) if match.group(1) in allowed else "",
        answer,
    )


def validate_citations(answer: str, evidence: list[Evidence]) -> None:
    allowed = {item.id for item in evidence}
    unknown = citation_ids(answer) - allowed
    if unknown:
        raise ValueError(f"Answer contains unknown citations: {sorted(unknown)}")
