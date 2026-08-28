"""Conditional chat workflow edges."""

from typing import Literal

from src.models.state import AgentState
from src.workflow.routing import (
    is_direct_figure_request,
    is_out_of_domain,
    needs_clarification,
)


def prepared_answer_route(state: AgentState) -> Literal["prepared", "figure"]:
    return "prepared" if state.get("prepared_answer") else "figure"


def figure_route(state: AgentState) -> Literal["prepared", "classify"]:
    prepared = bool(
        state.get("figure_description")
        and is_direct_figure_request(state["query"])
        and not state.get("image")
    )
    return "prepared" if prepared else "classify"


def domain_route(state: AgentState) -> Literal["reject", "clarify", "continue"]:
    decision = state.get("domain_decision")
    if is_out_of_domain(decision):
        return "reject"
    if needs_clarification(decision):
        return "clarify"
    return "continue"
