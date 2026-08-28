"""LangGraph workflow state."""

from typing import Any, Literal, TypedDict

from src.domain.models import DomainDecision
from src.knowledge.models import Evidence

ResponseSource = Literal[
    "prepared_answer", "figure_prepared", "generated", "out_of_domain", "clarification"
]
ConversationStatus = Literal["active", "ended"]


class AgentState(TypedDict):
    """State shared by chat preparation and answer resolution."""

    owner_id: str
    conversation_id: str
    query: str
    figure_id: str | None
    image: str | None
    prior_in_domain: bool
    domain_decision: DomainDecision | None
    conversation_history: list[dict[str, str]]
    figure_description: str | None
    evidence: list[Evidence]
    used_citation_ids: list[str]
    prepared_answer: str | None
    aggregated_context: list[dict[str, Any]]
    final_answer: str
    response_source: ResponseSource | None
    conversation_status: ConversationStatus
