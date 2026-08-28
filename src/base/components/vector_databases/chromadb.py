"""ChromaDB HTTP vector-store implementation."""

import re
from collections.abc import Sequence
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Metadata
from loguru import logger

from src.base.components.embeddings.base import BaseEmbedding
from src.base.components.vector_databases.base import BaseVectorDatabase, SearchHit
from src.config.settings import get_settings


class ChromaVectorDatabase(BaseVectorDatabase):
    def __init__(self, embedding: BaseEmbedding, collection_name: str = "default"):
        super().__init__(embedding)
        settings = get_settings()
        self._collection_name = collection_name
        self._client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        logger.info(
            "ChromaDB HTTP client configured: {}:{}/{}",
            settings.chroma_host,
            settings.chroma_port,
            collection_name,
        )

    def _collection(self) -> Collection:
        return self._client.get_or_create_collection(name=self._collection_name)

    def replace_source(
        self,
        source: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if len(ids) != len(texts) or len(texts) != len(metadatas):
            raise ValueError("Vector IDs, texts, and metadata must have equal lengths")

        collection = self._collection()
        collection.delete(where={"source": source})
        if texts:
            self._add(collection, ids, texts, metadatas)

    def upsert(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if len(ids) != len(texts) or len(texts) != len(metadatas):
            raise ValueError("Vector IDs, texts, and metadata must have equal lengths")
        if not ids:
            return
        collection = self._collection()
        collection.delete(ids=ids)
        self._add(collection, ids, texts, metadatas)

    def get_by_id(self, document_id: str) -> SearchHit | None:
        result = self._collection().get(
            ids=[document_id],
            include=["documents", "metadatas"],
        )
        if not result["ids"]:
            return None
        documents = result["documents"] or []
        metadatas = result["metadatas"] or []
        if not documents:
            return None
        metadata = metadatas[0] if metadatas else None
        return SearchHit(
            id=result["ids"][0],
            content=documents[0],
            metadata=dict(metadata) if metadata else {},
            distance=0.0,
        )

    def list_ids(self) -> list[str]:
        return self._collection().get(include=[])["ids"]

    def similarity_search(self, query: str, k: int = 5) -> list[SearchHit]:
        result = self._collection().query(
            query_embeddings=self.embedding.embed(query),
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        ids = result["ids"][0]
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []
        return [
            SearchHit(
                id=document_id,
                content=document,
                metadata=dict(metadata) if metadata else {},
                distance=distance,
            )
            for document_id, document, metadata, distance in zip(
                ids, documents, metadatas, distances, strict=True
            )
        ]

    def lexical_search(self, query: str, k: int = 5) -> list[SearchHit]:
        terms = {term.casefold() for term in re.findall(r"(?u)\b\w{2,}\b", query)}
        if not terms:
            return []
        result = self._collection().get(include=["documents", "metadatas"])
        documents = result["documents"] or []
        metadatas = result["metadatas"] or []
        hits: list[SearchHit] = []
        for index, document in enumerate(documents):
            document_terms = set(re.findall(r"(?u)\b\w{2,}\b", document.casefold()))
            overlap = len(terms & document_terms) / len(terms)
            if not overlap:
                continue
            metadata = metadatas[index] if index < len(metadatas) else None
            hits.append(
                SearchHit(
                    id=result["ids"][index],
                    content=document,
                    metadata=dict(metadata) if metadata else {},
                    distance=1.0 - overlap,
                )
            )
        return sorted(hits, key=lambda hit: hit.distance)[:k]

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection().delete(ids=ids)

    def _add(
        self,
        collection: Collection,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        chroma_metadata: list[Metadata] = list(metadatas)
        chroma_embeddings: list[Sequence[float] | Sequence[int]] = [
            embedding for embedding in self.embedding.embed_batch(texts)
        ]
        collection.add(
            ids=ids,
            documents=texts,
            embeddings=chroma_embeddings,
            metadatas=chroma_metadata,
        )
