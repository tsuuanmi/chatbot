"""Diagnostic hybrid retrieval endpoint."""

from typing import Any

from hayhooks import BasePipelineWrapper

from chatbot_app.retrieval import (
    get_hybrid_retriever,
)


def serialize_document(
    document: Any,
) -> dict[str, Any]:
    return {
        "id": document.id,
        "score": (
            float(document.score)
            if document.score is not None
            else None
        ),
        "content": document.content,
        "meta": {
            "no": document.meta.get("no"),
            "term": document.meta.get("term"),
            "topic": document.meta.get("topic"),
            "figure_id": document.meta.get(
                "figure_id"
            ),
            "source_id": document.meta.get(
                "source_id"
            ),
            "source_title": document.meta.get(
                "source_title"
            ),
            "source_authority": document.meta.get(
                "source_authority"
            ),
            "source_page_or_section": (
                document.meta.get(
                    "source_page_or_section"
                )
            ),
            "approval_status": document.meta.get(
                "approval_status"
            ),
        },
    }


class PipelineWrapper(BasePipelineWrapper):
    skip_mcp = True

    def setup(self) -> None:
        self.retriever = get_hybrid_retriever()

    async def run_api_async(
        self,
        query: str,
    ) -> dict[str, object]:
        result = await self.retriever.retrieve(
            query
        )

        return {
            "hybrid": [
                serialize_document(document)
                for document in result.hybrid
            ],
            "semantic": [
                serialize_document(document)
                for document in result.semantic
            ],
            "keyword": [
                serialize_document(document)
                for document in result.keyword
            ],
        }
