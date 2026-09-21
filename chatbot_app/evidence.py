"""Explicit approved-evidence policy."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from haystack import Document

from chatbot_app.citations import (
    citation_id_from_meta,
)
from chatbot_app.retrieval import (
    HybridRetrievalResult,
)
from chatbot_app.relevance import (
    is_semantically_relevant,
    minimum_semantic_score,
)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    document: Document
    citation_id: str
    semantic_score: float | None
    authoritative: bool

    def citation(self) -> dict[str, object]:
        meta = self.document.meta

        return {
            "id": self.citation_id,
            "source_id": meta.get("source_id"),
            "title": meta.get("source_title"),
            "authority": meta.get(
                "source_authority"
            ),
            "version": meta.get(
                "source_version"
            ),
            "section": meta.get(
                "source_page_or_section"
            ),
            "topic": meta.get("topic"),
            "authoritative": self.authoritative,
        }


class EvidencePolicy:
    """Allow only explicitly configured topics."""

    def __init__(self) -> None:
        path = Path(
            os.environ.get(
                "EVIDENCE_POLICY_FILE",
                "/app/data/policies/evidence_policy.json",
            )
        )

        if not path.is_file():
            raise RuntimeError(
                f"Evidence policy file not found: {path}"
            )

        with path.open(
            encoding="utf-8"
        ) as handle:
            config = json.load(handle)

        self.supporting_topics = frozenset(
            config["supporting_topics"]
        )

        self.authoritative_topics = frozenset(
            config["authoritative_topics"]
        )

        self.standard_max_evidence = int(
            config["standard_max_evidence"]
        )

        self.high_risk_max_evidence = int(
            config["high_risk_max_evidence"]
        )

        self.minimum_semantic_score = (
            minimum_semantic_score()
        )

    @property
    def has_authoritative_topics(self) -> bool:
        return bool(
            self.authoritative_topics
        )

    def select(
        self,
        retrieval: HybridRetrievalResult,
        *,
        high_risk: bool,
    ) -> list[EvidenceItem]:
        semantic_scores = {
            document.id: (
                float(document.score)
                if document.score is not None
                else None
            )
            for document in retrieval.semantic
        }

        if high_risk:
            permitted = self.authoritative_topics
            limit = self.high_risk_max_evidence
        else:
            permitted = (
                self.supporting_topics
                | self.authoritative_topics
            )
            limit = self.standard_max_evidence

        selected: list[EvidenceItem] = []

        for document in retrieval.hybrid:
            semantic_score = semantic_scores.get(
                document.id
            )

            if not is_semantically_relevant(
                semantic_score,
                self.minimum_semantic_score,
            ):
                continue

            meta = document.meta

            if (
                str(
                    meta.get(
                        "approval_status",
                        "",
                    )
                ).lower()
                != "approved"
            ):
                continue

            topic = str(
                meta.get("topic") or ""
            )

            if topic not in permitted:
                continue

            authoritative = (
                topic
                in self.authoritative_topics
            )

            selected.append(
                EvidenceItem(
                    document=document,
                    citation_id=(
                        citation_id_from_meta(
                            meta,
                            fallback_id=document.id,
                        )
                    ),
                    semantic_score=semantic_score,
                    authoritative=authoritative,
                )
            )

            if len(selected) >= limit:
                break

        return selected


@lru_cache
def get_evidence_policy() -> EvidencePolicy:
    return EvidencePolicy()
