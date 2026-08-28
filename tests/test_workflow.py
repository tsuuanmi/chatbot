"""Evidence-aware answer-cascade graph tests."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.models import DomainDecision, DomainLabel, DomainReason, RiskLevel
from src.models.state import AgentState
from src.workflow import graph


def domain(label: DomainLabel) -> DomainDecision:
    return DomainDecision(
        label=label,
        risk=RiskLevel.STANDARD,
        reason=(
            DomainReason.UNRELATED_TOPIC
            if label is DomainLabel.OUT_OF_DOMAIN
            else DomainReason.FORENSIC_GENETICS
        ),
        confidence=0.9,
    )


def state(query: str) -> AgentState:
    return {
        "owner_id": "client-a",
        "conversation_id": "conversation",
        "query": query,
        "figure_id": None,
        "image": None,
        "prior_in_domain": False,
        "domain_decision": None,
        "conversation_history": [],
        "figure_description": None,
        "evidence": [],
        "used_citation_ids": [],
        "prepared_answer": None,
        "aggregated_context": [],
        "final_answer": "",
        "response_source": None,
        "conversation_status": "active",
    }


@pytest.mark.asyncio
async def test_prepared_answer_ends_before_domain_classification() -> None:
    async def find_prepared(current: AgentState) -> dict[str, Any]:
        return {"prepared_answer": "Authoritative answer"}

    classify = AsyncMock(side_effect=AssertionError("domain classifier was called"))
    with (
        patch.object(graph, "find_prepared_answer", find_prepared),
        patch.object(graph, "classify_domain", classify),
    ):
        result = await graph.build_graph().compile().ainvoke(state("Exact question"))
    assert result["prepared_answer"] == "Authoritative answer"
    classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_out_of_domain_ends_before_history_and_retrieval() -> None:
    async def no_prepared(current: AgentState) -> dict[str, Any]:
        return {"prepared_answer": None}

    async def no_figure(current: AgentState) -> dict[str, Any]:
        return {"figure_description": None}

    async def no_prior(current: AgentState) -> dict[str, Any]:
        return {"prior_in_domain": False}

    async def reject(current: AgentState) -> dict[str, Any]:
        return {"domain_decision": domain(DomainLabel.OUT_OF_DOMAIN)}

    load_history = AsyncMock(side_effect=AssertionError("history was loaded"))
    retrieve = AsyncMock(side_effect=AssertionError("retrieval was called"))
    with (
        patch.object(graph, "find_prepared_answer", no_prepared),
        patch.object(graph, "resolve_figure_description", no_figure),
        patch.object(graph, "load_domain_context", no_prior),
        patch.object(graph, "classify_domain", reject),
        patch.object(graph, "load_conversation_history", load_history),
        patch.object(graph, "retrieve_knowledge", retrieve),
    ):
        result = await graph.build_graph().compile().ainvoke(state("Cách nấu phở"))
    assert result["domain_decision"].label is DomainLabel.OUT_OF_DOMAIN
    load_history.assert_not_awaited()
    retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_accepted_query_always_attempts_retrieval() -> None:
    async def no_prepared(current: AgentState) -> dict[str, Any]:
        return {"prepared_answer": None}

    async def no_figure(current: AgentState) -> dict[str, Any]:
        return {"figure_description": None}

    async def no_prior(current: AgentState) -> dict[str, Any]:
        return {"prior_in_domain": False}

    async def accept(current: AgentState) -> dict[str, Any]:
        return {"domain_decision": domain(DomainLabel.IN_DOMAIN)}

    async def history(current: AgentState) -> dict[str, Any]:
        return {"conversation_history": []}

    retrieve = AsyncMock(return_value={"evidence": []})

    async def aggregate(current: AgentState) -> dict[str, Any]:
        return {"aggregated_context": [{"role": "user", "content": current["query"]}]}

    with (
        patch.object(graph, "find_prepared_answer", no_prepared),
        patch.object(graph, "resolve_figure_description", no_figure),
        patch.object(graph, "load_domain_context", no_prior),
        patch.object(graph, "classify_domain", accept),
        patch.object(graph, "load_conversation_history", history),
        patch.object(graph, "retrieve_knowledge", retrieve),
        patch.object(graph, "aggregate_context", aggregate),
    ):
        await graph.build_graph().compile().ainvoke(state("DNA là gì?"))
    retrieve.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_figure_request_uses_precomputed_answer() -> None:
    async def no_prepared(current: AgentState) -> dict[str, Any]:
        return {"prepared_answer": None}

    async def figure(current: AgentState) -> dict[str, Any]:
        return {"figure_id": "heatmap1", "figure_description": "Stored heatmap"}

    classify = AsyncMock(side_effect=AssertionError("domain classifier was called"))
    current = state("Phân tích heatmap1")
    current["figure_id"] = "heatmap1"
    with (
        patch.object(graph, "find_prepared_answer", no_prepared),
        patch.object(graph, "resolve_figure_description", figure),
        patch.object(graph, "classify_domain", classify),
    ):
        result = await graph.build_graph().compile().ainvoke(current)
    assert result["figure_description"] == "Stored heatmap"
    classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_unindexed_configured_figure_is_not_inferred_live() -> None:
    store = MagicMock()
    store.get.return_value = None
    container = SimpleNamespace(figure_descriptions=store)
    current = state("Mô tả hình bar3")
    current["figure_id"] = "bar3"
    with patch("src.workflow.nodes.get_container", return_value=container):
        with pytest.raises(RuntimeError, match="has not been indexed"):
            await graph.resolve_figure_description(current)
