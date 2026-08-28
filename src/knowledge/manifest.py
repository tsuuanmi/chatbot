"""Validated source manifests for controlled PDF knowledge ingestion."""

import hashlib
import json
import re
from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SOURCE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{2,127}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class SourceStatus(StrEnum):
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class AccessClass(StrEnum):
    INTERNAL = "internal"


class SourceManifest(BaseModel):
    """Auditable release decision for one controlled source version."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    file: str
    title: str = Field(min_length=3)
    authority: str = Field(min_length=2)
    version: str = Field(min_length=1)
    effective_date: date
    reviewed_at: date
    reviewer: str = Field(min_length=2)
    approver: str = Field(min_length=2)
    approval_status: SourceStatus
    access_class: AccessClass
    sha256: str
    supersedes: str | None = None
    max_chunks: int = Field(default=1000, ge=1, le=1000)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        if not _SOURCE_ID_PATTERN.fullmatch(value):
            raise ValueError("source_id must be a stable lowercase identifier")
        return value

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        path = Path(value)
        if path.name != value or path.suffix.casefold() != ".pdf":
            raise ValueError("file must be one PDF filename without a path")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        digest = value.casefold()
        if not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError("sha256 must contain 64 hexadecimal characters")
        return digest

    @model_validator(mode="after")
    def validate_release(self) -> "SourceManifest":
        if self.reviewer.casefold() == self.approver.casefold():
            raise ValueError("reviewer and approver must be different")
        today = date.today()
        if self.reviewed_at > today:
            raise ValueError("reviewed_at cannot be in the future")
        if (
            self.approval_status is SourceStatus.APPROVED
            and self.effective_date > today
        ):
            raise ValueError("approved source is not yet effective")
        return self

    @classmethod
    def load(cls, path: Path) -> "SourceManifest":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid manifest {path.name}: {error}") from error
        return cls.model_validate(payload)

    def verify_file(self, directory: Path) -> Path:
        source_path = directory / self.file
        if not source_path.is_file():
            raise ValueError(f"Manifest source file does not exist: {self.file}")
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if digest != self.sha256:
            raise ValueError(f"SHA-256 mismatch for {self.file}")
        return source_path
