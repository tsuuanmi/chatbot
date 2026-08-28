"""Approved-source semantic retrieval for chat evidence."""

import asyncio

from loguru import logger

from src.base.components.vector_databases.base import BaseVectorDatabase
from src.knowledge.models import ApprovalStatus, Evidence, KnowledgeSource


class KnowledgeRetriever:
    def __init__(
        self,
        database: BaseVectorDatabase,
        *,
        top_k: int,
        max_distance: float,
    ) -> None:
        self._database = database
        self._top_k = top_k
        self._max_distance = max_distance

    async def retrieve(self, query: str) -> list[Evidence]:
        try:
            semantic_hits, lexical_hits = await asyncio.gather(
                asyncio.to_thread(self._database.similarity_search, query, self._top_k),
                asyncio.to_thread(self._database.lexical_search, query, self._top_k),
            )
        except Exception:
            logger.exception("Knowledge retrieval failed")
            return []

        combined = {hit.id: hit for hit in semantic_hits}
        for hit in lexical_hits:
            existing = combined.get(hit.id)
            if existing is None or hit.distance < existing.distance:
                combined[hit.id] = hit

        evidence: list[Evidence] = []
        for hit in sorted(combined.values(), key=lambda item: item.distance):
            metadata = hit.metadata
            if hit.distance > self._max_distance:
                continue
            if metadata.get("approval_status") != ApprovalStatus.APPROVED:
                continue
            source_id = str(metadata.get("source_id") or metadata.get("source") or "")
            evidence.append(
                Evidence(
                    id=hit.id,
                    content=hit.content,
                    distance=hit.distance,
                    source=KnowledgeSource(
                        id=source_id,
                        title=str(metadata.get("source_title") or source_id),
                        authority=str(metadata.get("source_authority") or ""),
                        version=str(metadata.get("source_version") or ""),
                        page_or_section=str(
                            metadata.get("source_page_or_section")
                            or metadata.get("page")
                            or ""
                        ),
                        approval_status=ApprovalStatus.APPROVED,
                    ),
                    metadata=metadata,
                )
            )
            if len(evidence) >= self._top_k:
                break
        logger.info("[knowledge] {} approved relevant hits", len(evidence))
        return evidence
