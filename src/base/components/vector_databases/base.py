"""Vector database interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.base.components.embeddings.base import BaseEmbedding


@dataclass(frozen=True, slots=True)
class SearchHit:
    id: str
    content: str
    metadata: dict[str, Any]
    distance: float


class BaseVectorDatabase(ABC):
    def __init__(self, embedding: BaseEmbedding) -> None:
        self.embedding = embedding

    def healthcheck(self) -> None:
        """Verify that the backing store and collection are reachable."""
        self.list_ids()

    @abstractmethod
    def replace_source(
        self,
        source: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    @abstractmethod
    def upsert(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None: ...

    @abstractmethod
    def get_by_id(self, document_id: str) -> SearchHit | None: ...

    @abstractmethod
    def list_ids(self) -> list[str]: ...

    @abstractmethod
    def similarity_search(self, query: str, k: int = 5) -> list[SearchHit]: ...

    @abstractmethod
    def lexical_search(self, query: str, k: int = 5) -> list[SearchHit]: ...

    @abstractmethod
    def delete(self, ids: list[str]) -> None: ...
