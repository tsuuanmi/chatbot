"""Approved normalized exact-match answers."""

from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from chatbot_app.citations import citation_id_from_meta


@dataclass(frozen=True, slots=True)
class PreparedAnswer:
    number: str
    question: str
    answer: str
    aliases: tuple[str, ...]
    topic: str
    figure_id: str | None
    source_id: str
    source_title: str
    source_authority: str
    source_version: str
    source_page_or_section: str
    approval_status: str

    @property
    def citation_id(self) -> str:
        return citation_id_from_meta(
            {
                "source_id": self.source_id,
                "no": self.number,
            },
            fallback_id=f"prepared-{self.number}",
        )

    def citation(self) -> dict[str, object]:
        return {
            "id": self.citation_id,
            "source_id": self.source_id,
            "title": self.source_title,
            "authority": self.source_authority,
            "version": self.source_version,
            "section": self.source_page_or_section,
            "topic": self.topic,
            "authoritative": False,
        }


class PreparedAnswerRepository:
    """Conservative exact-match access to approved TSV records."""

    def __init__(self) -> None:
        path = Path(
            os.environ.get(
                "KNOWLEDGE_BASE_FILE",
                "/app/data/documents/knowledge_base.tsv",
            )
        )

        if not path.is_file():
            raise RuntimeError(
                f"Knowledge base file not found: {path}"
            )

        answers: dict[str, PreparedAnswer] = {}

        with path.open(
            encoding="utf-8",
            newline="",
        ) as handle:
            reader = csv.DictReader(
                handle,
                delimiter="\t",
            )

            for row in reader:
                if (
                    row.get("approval_status", "")
                    .strip()
                    .lower()
                    != "approved"
                ):
                    continue

                question = row.get("term", "").strip()
                answer = row.get("description", "").strip()

                if not question or not answer:
                    continue

                entry = PreparedAnswer(
                    number=row.get("no", "").strip(),
                    question=question,
                    answer=answer,
                    aliases=tuple(
                        value.strip()
                        for value in row.get(
                            "aliases",
                            "",
                        ).split("|")
                        if value.strip()
                    ),
                    topic=row.get("topic", "").strip(),
                    figure_id=(
                        row.get("figure_id", "").strip()
                        or None
                    ),
                    source_id=row.get(
                        "source_id",
                        "",
                    ).strip(),
                    source_title=row.get(
                        "source_title",
                        "",
                    ).strip(),
                    source_authority=row.get(
                        "source_authority",
                        "",
                    ).strip(),
                    source_version=row.get(
                        "source_version",
                        "",
                    ).strip(),
                    source_page_or_section=row.get(
                        "source_page_or_section",
                        "",
                    ).strip(),
                    approval_status="approved",
                )

                for value in (
                    entry.question,
                    *entry.aliases,
                ):
                    answers[self._normalize(value)] = entry

        self._answers = answers

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize(
            "NFKC",
            text,
        ).casefold()

        normalized = re.sub(
            r"[^\w\s]",
            " ",
            normalized,
            flags=re.UNICODE,
        )

        return " ".join(normalized.split())

    def find(
        self,
        query: str,
    ) -> PreparedAnswer | None:
        return self._answers.get(
            self._normalize(query)
        )


@lru_cache
def get_prepared_answers() -> PreparedAnswerRepository:
    return PreparedAnswerRepository()
