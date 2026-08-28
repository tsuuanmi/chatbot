"""API and routing schemas."""

import base64
import binascii
from typing import Literal

from src.knowledge.models import KnowledgeSource

from pydantic import BaseModel, Field, field_validator


ResponseSource = Literal[
    "prepared_answer",
    "figure_prepared",
    "generated",
    "out_of_domain",
    "clarification",
]
ConversationStatus = Literal["active", "ended"]


class ChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=10_000)
    figure_id: str | None = Field(default=None, max_length=128)
    image: str | None = Field(default=None, max_length=10_000_000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be blank")
        return query

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        if value is None:
            return None
        image = value.strip()
        payload = image
        if image.startswith("data:image/") and ";base64," in image:
            payload = image.split(",", 1)[1]
        try:
            base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("image must be a base64 image or data URL") from error
        return image


class Citation(BaseModel):
    id: str
    source: KnowledgeSource


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    source: ResponseSource
    conversation_status: ConversationStatus = "active"
    citations: list[Citation] = Field(default_factory=list)


class StreamingChatChunk(BaseModel):
    type: Literal["start", "chunk", "end", "error"]
    conversation_id: str
    content: str | None = None
    source: ResponseSource | None = None
    error: str | None = None
    conversation_status: ConversationStatus | None = None
    citations: list[Citation] | None = None
