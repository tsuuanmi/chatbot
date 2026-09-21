"""Shared CPU-first retrieval infrastructure."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from haystack import Document, Pipeline
from haystack.components.joiners import DocumentJoiner
from haystack.utils import Secret

from chatbot_app.database import postgres_connection_string
from haystack_integrations.components.embedders.fastembed import (
    FastembedDocumentEmbedder,
    FastembedTextEmbedder,
)
from haystack_integrations.components.retrievers.pgvector import (
    PgvectorEmbeddingRetriever,
    PgvectorKeywordRetriever,
)
from haystack_integrations.document_stores.pgvector import (
    PgvectorDocumentStore,
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value


def build_document_store(
    *,
    recreate_table: bool = False,
) -> PgvectorDocumentStore:
    return PgvectorDocumentStore(
        connection_string=Secret.from_token(
            postgres_connection_string()
        ),
        create_extension=False,
        table_name="knowledge_documents",
        language="simple",
        embedding_dimension=int(
            _required_env(
                "EMBEDDING_DIMENSION"
            )
        ),
        vector_function="cosine_similarity",
        recreate_table=recreate_table,
        search_strategy="exact_nearest_neighbor",
    )


def build_text_embedder() -> FastembedTextEmbedder:
    return FastembedTextEmbedder(
        model=_required_env(
            "EMBEDDING_MODEL"
        ),
        cache_dir=_required_env(
            "FASTEMBED_CACHE_PATH"
        ),
        threads=int(
            os.environ.get(
                "EMBEDDING_THREADS",
                "4",
            )
        ),
        progress_bar=False,
        local_files_only=True,
    )


def build_document_embedder() -> FastembedDocumentEmbedder:
    return FastembedDocumentEmbedder(
        model=_required_env(
            "EMBEDDING_MODEL"
        ),
        cache_dir=_required_env(
            "FASTEMBED_CACHE_PATH"
        ),
        threads=int(
            os.environ.get(
                "EMBEDDING_THREADS",
                "4",
            )
        ),
        batch_size=64,
        progress_bar=False,
        local_files_only=True,
    )


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    hybrid: list[Document]
    semantic: list[Document]
    keyword: list[Document]


class HybridKnowledgeRetriever:
    """One shared hybrid retrieval pipeline."""

    def __init__(self) -> None:
        document_store = build_document_store()

        pipeline = Pipeline()

        pipeline.add_component(
            "embedder",
            build_text_embedder(),
        )

        pipeline.add_component(
            "semantic",
            PgvectorEmbeddingRetriever(
                document_store=document_store,
                top_k=8,
            ),
        )

        pipeline.add_component(
            "keyword",
            PgvectorKeywordRetriever(
                document_store=document_store,
                top_k=8,
            ),
        )

        pipeline.add_component(
            "joiner",
            DocumentJoiner(
                join_mode="reciprocal_rank_fusion",
                top_k=5,
            ),
        )

        pipeline.connect(
            "embedder.embedding",
            "semantic.query_embedding",
        )

        pipeline.connect(
            "semantic.documents",
            "joiner.documents",
        )

        pipeline.connect(
            "keyword.documents",
            "joiner.documents",
        )

        self.pipeline = pipeline

    async def retrieve(
        self,
        query: str,
    ) -> HybridRetrievalResult:
        result = await self.pipeline.run_async(
            {
                "embedder": {
                    "text": query,
                },
                "keyword": {
                    "query": query,
                },
            },
            include_outputs_from={
                "semantic",
                "keyword",
            },
        )

        return HybridRetrievalResult(
            hybrid=result["joiner"]["documents"],
            semantic=result["semantic"]["documents"],
            keyword=result["keyword"]["documents"],
        )


@lru_cache
def get_hybrid_retriever() -> HybridKnowledgeRetriever:
    return HybridKnowledgeRetriever()
