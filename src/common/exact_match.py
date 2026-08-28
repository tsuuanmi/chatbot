"""Prepared-answer repository backed by approved knowledge records."""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from loguru import logger

from src.common.knowledge_base import KnowledgeEntry, load_knowledge_base
from src.knowledge.models import ApprovalStatus


class PreparedAnswerRepository:
    """Normalized exact access to approved prepared answers."""

    def __init__(self, path: str | Path | None = None) -> None:
        entries = [
            entry
            for entry in load_knowledge_base(path)
            if entry.approval_status == ApprovalStatus.APPROVED
        ]
        self._answers = {
            self._normalize(question): entry
            for entry in entries
            for question in (entry.question, *entry.aliases)
        }
        if entries:
            logger.info("Loaded {} approved prepared answers", len(entries))
        else:
            logger.warning("Prepared-answer knowledge base is empty")

    def find(self, question: str) -> KnowledgeEntry | None:
        return self._answers.get(self._normalize(question))

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
        return " ".join(normalized.split())


@lru_cache
def get_prepared_answers() -> PreparedAnswerRepository:
    return PreparedAnswerRepository()
