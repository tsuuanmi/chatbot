"""Deterministic routing helpers outside semantic domain classification."""

import re

from src.domain.models import DomainDecision, DomainLabel

_FIGURE_ID_PATTERN = re.compile(
    r"(?<!\w)(?P<figure_id>"
    r"heatmap\d+|bar\d+|pie\d+|scatter\d+|ridge\d+|network\d+|"
    r"tree\d+|venn\d+|cloud\d+|admixture\d+|semipie\d+"
    r")(?!\w)",
    re.IGNORECASE,
)


def resolve_figure_id(query: str, figure_id: str | None = None) -> str | None:
    """Return the explicit or query-embedded configured figure identifier."""
    if figure_id:
        return figure_id
    match = _FIGURE_ID_PATTERN.search(query)
    return match.group("figure_id").lower() if match else None


def is_direct_figure_request(query: str) -> bool:
    """Return whether a figure request can use its canonical description verbatim."""
    normalized = " ".join(query.split())
    asks_for_analysis = re.search(
        r"(?<!\w)(?:mô\s+tả|miêu\s+tả|giải\s+thích|phân\s+tích|"
        r"describe|explain|analy[sz]e)(?!\w)",
        normalized,
        re.IGNORECASE,
    )
    asks_specific_question = re.search(
        r"(?<!\w)(?:tại\s+sao|vì\s+sao|bao\s+nhiêu|so\s+sánh|"
        r"why|how\s+many|compare)(?!\w)",
        normalized,
        re.IGNORECASE,
    )
    return bool(asks_for_analysis and not asks_specific_question)


def is_out_of_domain(decision: DomainDecision | None) -> bool:
    return bool(decision and decision.label is DomainLabel.OUT_OF_DOMAIN)


def needs_clarification(decision: DomainDecision | None) -> bool:
    return bool(decision and decision.label is DomainLabel.CLARIFY)
