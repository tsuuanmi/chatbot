"""Prepared-answer and workflow resolution tests."""

from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.exact_match import PreparedAnswerRepository
from src.domain.models import DomainDecision, DomainLabel, DomainReason, RiskLevel
from src.workflow.graph import (
    CLARIFICATION_MESSAGE,
    OUT_OF_DOMAIN_MESSAGE,
    run_workflow,
    stream_workflow,
)


def decision(label: DomainLabel) -> DomainDecision:
    reason = (
        DomainReason.UNRELATED_TOPIC
        if label is DomainLabel.OUT_OF_DOMAIN
        else DomainReason.AMBIGUOUS_CONTEXT
    )
    return DomainDecision(
        label=label,
        risk=RiskLevel.STANDARD,
        reason=reason,
        confidence=0.9,
    )


@pytest.fixture
def prepared_state() -> dict:
    return {
        "prepared_answer": "Prepared response",
        "domain_decision": None,
        "evidence": [],
        "used_citation_ids": [],
        "aggregated_context": [],
        "conversation_status": "active",
        "response_source": None,
        "figure_description": None,
    }


def test_prepared_answer_repository_normalizes_approved_match(tmp_path: Path) -> None:
    path = tmp_path / "answers.tsv"
    path.write_text(
        "no\tterm\tdescription\tkeywords\ttopic\tfigure_id\tsource_id\t"
        "source_title\tsource_authority\tsource_version\t"
        "source_page_or_section\tapproval_status\n"
        "1\tQuestion?\tAnswer.\tkey\ttopic\tfigure1\tsource\ttitle\t"
        "authority\t1\tsection\tapproved\n",
        encoding="utf-8",
    )
    repository = PreparedAnswerRepository(path)
    answer = repository.find("  QUESTION!  ")
    assert answer is not None
    assert answer.answer == "Answer."
    assert answer.figure_id == "figure1"


@pytest.mark.asyncio
async def test_run_workflow_returns_prepared_answer(prepared_state: dict) -> None:
    with patch(
        "src.workflow.graph.prepare_workflow",
        new=AsyncMock(return_value=prepared_state),
    ):
        result = await run_workflow("conversation", "Question?")
    assert result["final_answer"] == "Prepared response"
    assert result["response_source"] == "prepared_answer"


@pytest.mark.asyncio
async def test_run_workflow_generates_without_evidence(prepared_state: dict) -> None:
    prepared_state.update(
        {
            "prepared_answer": None,
            "domain_decision": DomainDecision(
                label=DomainLabel.IN_DOMAIN,
                risk=RiskLevel.STANDARD,
                reason=DomainReason.FORENSIC_GENETICS,
                confidence=0.9,
            ),
            "aggregated_context": [{"role": "user", "content": "Question"}],
        }
    )
    client = MagicMock()
    client.chat = AsyncMock(return_value="Generated answer")
    with (
        patch(
            "src.workflow.graph.prepare_workflow",
            new=AsyncMock(return_value=prepared_state),
        ),
        patch("src.workflow.graph.get_llm_client", return_value=client),
    ):
        result = await run_workflow("conversation", "Question")
    assert result["final_answer"] == "Generated answer"
    assert result["response_source"] == "generated"


@pytest.mark.asyncio
async def test_run_workflow_rejects_out_of_domain(prepared_state: dict) -> None:
    prepared_state.update(
        {
            "prepared_answer": None,
            "domain_decision": decision(DomainLabel.OUT_OF_DOMAIN),
        }
    )
    with patch(
        "src.workflow.graph.prepare_workflow",
        new=AsyncMock(return_value=prepared_state),
    ):
        result = await run_workflow("conversation", "Cooking")
    assert result["final_answer"] == OUT_OF_DOMAIN_MESSAGE
    assert result["response_source"] == "out_of_domain"
    assert result["conversation_status"] == "ended"


@pytest.mark.asyncio
async def test_run_workflow_requests_clarification(prepared_state: dict) -> None:
    prepared_state.update(
        {
            "prepared_answer": None,
            "domain_decision": decision(DomainLabel.CLARIFY),
        }
    )
    with patch(
        "src.workflow.graph.prepare_workflow",
        new=AsyncMock(return_value=prepared_state),
    ):
        result = await run_workflow("conversation", "Phân tích kết quả này")
    assert result["final_answer"] == CLARIFICATION_MESSAGE
    assert result["response_source"] == "clarification"
    assert result["conversation_status"] == "active"


@pytest.mark.asyncio
async def test_stream_workflow_validates_then_streams_tokens(
    prepared_state: dict,
) -> None:
    prepared_state.update(
        {
            "prepared_answer": None,
            "domain_decision": DomainDecision(
                label=DomainLabel.IN_DOMAIN,
                risk=RiskLevel.STANDARD,
                reason=DomainReason.FORENSIC_GENETICS,
                confidence=0.9,
            ),
            "aggregated_context": [{"role": "user", "content": "Question"}],
        }
    )

    async def tokens(**kwargs) -> AsyncGenerator[str, None]:
        yield "one"
        yield "two"

    client = MagicMock()
    client.stream_chat.side_effect = tokens
    with (
        patch(
            "src.workflow.graph.prepare_workflow",
            new=AsyncMock(return_value=prepared_state),
        ),
        patch("src.workflow.graph.get_llm_client", return_value=client),
    ):
        state, stream = await stream_workflow("conversation", "Question")
        result = [token async for token in stream]
    assert state["response_source"] == "generated"
    assert result == ["one", "two"]
    assert client.stream_chat.call_args.kwargs["allowed_citations"] == set()
