"""Stable production HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from chatbot_app.auth import current_identity
from chatbot_app.capacity import GenerationBusyError
from chatbot_app.forensic_chat import get_forensic_chat
from chatbot_app.history import (
    ConversationOwnershipError,
    get_conversation_repository,
)
from chatbot_app.readiness import get_readiness


logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Canonical public chat request."""

    query: str
    conversation_id: UUID | None = None
    figure_id: str | None = None
    image: str | None = None


def _error(
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


@router.get("/ready")
async def ready():
    """Dependency readiness. Authentication is enforced by middleware."""

    try:
        return await get_readiness().check()
    except Exception:
        logger.exception(
            "Public readiness check failed"
        )

        return _error(
            503,
            "service_unavailable",
            "Chatbot dependencies are not ready",
        )


@router.post("/api/v1/chat")
async def chat(
    payload: ChatRequest,
):
    """Run one canonical chat request."""

    service = get_forensic_chat()

    try:
        return await service.answer(
            payload.query,
            (
                str(payload.conversation_id)
                if payload.conversation_id is not None
                else None
            ),
            figure_id=payload.figure_id,
            image=payload.image,
        )

    except GenerationBusyError as error:
        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(
                    error.retry_after_seconds
                ),
            },
            content={
                "error": {
                    "code": "busy",
                    "message": (
                        "Model generation capacity is busy"
                    ),
                    "retry_after_seconds": (
                        error.retry_after_seconds
                    ),
                }
            },
        )

    except ValueError as error:
        return _error(
            422,
            "validation_error",
            str(error),
        )

    except ConversationOwnershipError:
        return _error(
            404,
            "not_found",
            "Conversation not found",
        )


@router.post("/api/v1/chat/stream")
async def stream_chat(
    payload: ChatRequest,
) -> StreamingResponse:
    """Stream one canonical chat request as JSON SSE events."""

    service = get_forensic_chat()

    async def events():
        try:
            async for event in service.stream_answer(
                payload.query,
                (
                    str(payload.conversation_id)
                    if payload.conversation_id is not None
                    else None
                ),
                figure_id=payload.figure_id,
                image=payload.image,
            ):
                yield (
                    "data: "
                    + json.dumps(
                        event,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n\n"
                )

        except asyncio.CancelledError:
            raise

        except GenerationBusyError as error:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {
                            "code": "busy",
                            "message": (
                                "Model generation capacity is busy"
                            ),
                            "retry_after_seconds": (
                                error.retry_after_seconds
                            ),
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )
        except ValueError as error:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {
                            "code": "validation_error",
                            "message": str(error),
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )

        except ConversationOwnershipError:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {
                            "code": "not_found",
                            "message": "Conversation not found",
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )

        except Exception:
            logger.exception(
                "Public chat stream failed"
            )

            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "error": {
                            "code": "internal_error",
                            "message": (
                                "An unexpected error occurred"
                            ),
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/api/v1/conversations/{conversation_id}"
)
async def delete_conversation(
    conversation_id: UUID,
):
    """Delete an authenticated owner's conversation."""

    repository = get_conversation_repository()

    try:
        deleted_turns = (
            await repository.delete_conversation(
                conversation_id,
                owner_id=(
                    current_identity().owner_id
                ),
            )
        )

    except ConversationOwnershipError:
        return _error(
            404,
            "not_found",
            "Conversation not found",
        )

    return {
        "status": "success",
        "deleted_turns": deleted_turns,
    }
