"""Primary chat API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from src.api.auth import AuthenticatedClient, require_client
from src.api.capacity import reserve_model_capacity
from src.api.sse_formatter import format_sse
from src.common.schemas import Citation, ChatRequest, ChatResponse, StreamingChatChunk
from src.database.history_service import HistoryService, get_history_service
from src.domain.models import DomainLabel, RiskLevel
from src.knowledge.citations import citation_ids
from src.models.state import AgentState
from src.workflow.graph import run_workflow, stream_workflow

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: Annotated[AuthenticatedClient, Depends(require_client)],
    _capacity: Annotated[None, Depends(reserve_model_capacity)],
) -> ChatResponse:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    history = get_history_service()
    await _claim_conversation(history, conversation_id, client.client_id)
    result = await run_workflow(
        conversation_id=conversation_id,
        query=request.query,
        figure_id=request.figure_id,
        image=request.image,
        owner_id=client.client_id,
    )
    answer = result["final_answer"]
    if answer:
        try:
            label, risk = _decision(result)
            await history.save_turn(
                conversation_id,
                request.query,
                answer,
                label,
                risk,
                owner_id=client.client_id,
            )
        except Exception:
            logger.exception("Failed to persist conversation {}", conversation_id)

    source = result["response_source"]
    if source is None:
        raise RuntimeError("Workflow completed without a response source")
    return ChatResponse(
        response=answer,
        conversation_id=conversation_id,
        source=source,
        conversation_status=result["conversation_status"],
        citations=_citations(result),
    )


@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    client: Annotated[AuthenticatedClient, Depends(require_client)],
    _capacity: Annotated[None, Depends(reserve_model_capacity)],
) -> StreamingResponse:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    history = get_history_service()
    await _claim_conversation(history, conversation_id, client.client_id)
    state, token_stream = await stream_workflow(
        conversation_id=conversation_id,
        query=request.query,
        figure_id=request.figure_id,
        image=request.image,
        owner_id=client.client_id,
    )

    async def events() -> AsyncGenerator[str, None]:
        parts: list[str] = []
        source = state["response_source"]
        if source is None:
            raise RuntimeError("Workflow stream started without a response source")
        status = state["conversation_status"]
        yield format_sse(
            StreamingChatChunk(
                type="start",
                conversation_id=conversation_id,
                source=source,
            )
        )
        try:
            async for token in token_stream:
                if not token:
                    continue
                parts.append(token)
                yield format_sse(
                    StreamingChatChunk(
                        type="chunk",
                        conversation_id=conversation_id,
                        content=token,
                        source=source,
                    )
                )

            answer = "".join(parts)
            state["used_citation_ids"] = sorted(citation_ids(answer))
            if answer:
                try:
                    label, risk = _decision(state)
                    await history.save_turn(
                        conversation_id,
                        request.query,
                        answer,
                        label,
                        risk,
                        owner_id=client.client_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist streamed conversation {}", conversation_id
                    )
            yield format_sse(
                StreamingChatChunk(
                    type="end",
                    conversation_id=conversation_id,
                    source=source,
                    conversation_status=status,
                    citations=_citations(state),
                )
            )
        except Exception:
            logger.exception("Chat stream failed for {}", conversation_id)
            yield format_sse(
                StreamingChatChunk(
                    type="error",
                    conversation_id=conversation_id,
                    source=source,
                    error="An unexpected error occurred",
                    conversation_status=status,
                )
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _claim_conversation(
    history: HistoryService, conversation_id: str, owner_id: str
) -> None:
    if not await history.claim_conversation(conversation_id, owner_id=owner_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )


def _citations(state: AgentState) -> list[Citation]:
    used_ids = set(state.get("used_citation_ids", []))
    return [
        Citation(id=item.id, source=item.source)
        for item in state.get("evidence", [])
        if item.id in used_ids
    ]


def _decision(state: AgentState) -> tuple[DomainLabel, RiskLevel]:
    decision = state.get("domain_decision")
    if decision is None:
        return DomainLabel.IN_DOMAIN, RiskLevel.STANDARD
    return decision.label, decision.risk


@router.delete("/conversations/{conversation_id}")
async def clear_history(
    conversation_id: str,
    client: Annotated[AuthenticatedClient, Depends(require_client)],
) -> dict[str, int | str]:
    history = get_history_service()
    owner_id = await history.get_conversation_owner(conversation_id)
    if owner_id is not None and owner_id != client.client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    deleted_turns = await history.clear_history(
        conversation_id, owner_id=client.client_id
    )
    return {"status": "success", "deleted_turns": deleted_turns}
