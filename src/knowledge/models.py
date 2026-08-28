"""Typed knowledge provenance and retrieved evidence."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ApprovalStatus(StrEnum):
    APPROVED = "approved"


class KnowledgeSource(BaseModel):
    id: str
    title: str
    authority: str
    version: str
    page_or_section: str = ""
    approval_status: ApprovalStatus


class Evidence(BaseModel):
    id: str
    content: str
    distance: float
    source: KnowledgeSource
    metadata: dict[str, Any]
