"""Approved retrieval and citation tests."""

from unittest.mock import MagicMock

import pytest

from src.base.components.vector_databases.base import SearchHit
from src.knowledge.citations import sanitize_citations, validate_citations
from src.knowledge.models import ApprovalStatus, Evidence, KnowledgeSource
from src.knowledge.retriever import KnowledgeRetriever


@pytest.mark.asyncio
async def test_retriever_filters_distance_and_unapproved_hits() -> None:
    database = MagicMock()
    database.lexical_search.return_value = []
    database.similarity_search.return_value = [
        SearchHit(
            "knowledge:1",
            "approved",
            {
                "approval_status": "approved",
                "source_id": "source",
                "source_title": "Title",
                "source_authority": "Authority",
                "source_version": "1",
            },
            0.2,
        ),
        SearchHit("knowledge:2", "draft", {"approval_status": "draft"}, 0.1),
        SearchHit("knowledge:3", "distant", {"approval_status": "approved"}, 1.2),
    ]
    retriever = KnowledgeRetriever(database, top_k=5, max_distance=0.85)
    evidence = await retriever.retrieve("query")
    assert [item.id for item in evidence] == ["knowledge:1"]


def test_citation_validation_rejects_unknown_ids() -> None:
    evidence = [
        Evidence(
            id="knowledge:1",
            content="content",
            distance=0.1,
            source=KnowledgeSource(
                id="source",
                title="Title",
                authority="Authority",
                version="1",
                approval_status=ApprovalStatus.APPROVED,
            ),
            metadata={},
        )
    ]
    validate_citations("Supported [knowledge:1]", evidence)
    with pytest.raises(ValueError, match="unknown citations"):
        validate_citations("Invented [knowledge:999]", evidence)
    assert sanitize_citations("Invented [knowledge:999]", evidence) == "Invented "
