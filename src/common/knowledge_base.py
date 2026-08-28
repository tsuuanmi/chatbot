"""Typed access to the project TSV knowledge base."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KnowledgeEntry:
    """A validated question-and-answer entry with auditable provenance."""

    number: int
    question: str
    answer: str
    keywords: str = ""
    aliases: tuple[str, ...] = ()
    topic: str = ""
    figure_id: str | None = None
    source_id: str = ""
    source_title: str = ""
    source_authority: str = ""
    source_version: str = ""
    source_page_or_section: str = ""
    effective_date: str = ""
    reviewed_at: str = ""
    reviewer: str = ""
    approval_status: str = "draft"


def default_knowledge_base_path() -> Path:
    """Return the packaged project knowledge-base path."""
    return Path(__file__).parents[2] / "data/documents/knowledge_base.tsv"


def load_knowledge_base(path: str | Path | None = None) -> list[KnowledgeEntry]:
    """Load valid entries from a UTF-8 tab-separated knowledge base."""
    source = Path(path) if path else default_knowledge_base_path()
    if not source.is_file():
        return []

    entries: list[KnowledgeEntry] = []
    with source.open(encoding="utf-8", newline="") as file:
        for index, row in enumerate(csv.DictReader(file, delimiter="\t"), start=1):
            question = (row.get("term") or "").strip()
            answer = (row.get("description") or "").strip()
            if not question or not answer:
                continue
            entries.append(
                KnowledgeEntry(
                    number=int((row.get("no") or index)),
                    question=question,
                    answer=answer,
                    keywords=(row.get("keywords") or "").strip(),
                    aliases=tuple(
                        alias.strip()
                        for alias in (row.get("aliases") or "").split("|")
                        if alias.strip()
                    ),
                    topic=(row.get("topic") or "").strip(),
                    figure_id=(row.get("figure_id") or "").strip() or None,
                    source_id=(row.get("source_id") or "").strip(),
                    source_title=(row.get("source_title") or "").strip(),
                    source_authority=(row.get("source_authority") or "").strip(),
                    source_version=(row.get("source_version") or "").strip(),
                    source_page_or_section=(
                        row.get("source_page_or_section") or ""
                    ).strip(),
                    effective_date=(row.get("effective_date") or "").strip(),
                    reviewed_at=(row.get("reviewed_at") or "").strip(),
                    reviewer=(row.get("reviewer") or "").strip(),
                    approval_status=(row.get("approval_status") or "draft").strip(),
                )
            )
    return entries
