"""Persistence boundary for precomputed figure descriptions."""

from src.base.components.vector_databases.base import BaseVectorDatabase
from src.figures.models import FigureDescription

FIGURE_SOURCE = "figures"


class FigureDescriptionStore:
    """Store and retrieve figure descriptions by exact figure identifier."""

    def __init__(self, vector_database: BaseVectorDatabase) -> None:
        self._vector_database = vector_database

    def healthcheck(self) -> int:
        """Return the number of reachable precomputed figure records."""
        self._vector_database.healthcheck()
        return len(self._vector_database.list_ids())

    def get(self, figure_id: str) -> FigureDescription | None:
        record = self._vector_database.get_by_id(self._document_id(figure_id))
        if record is None:
            return None
        content_hash = record.metadata.get("content_hash")
        stored_figure_id = record.metadata.get("figure_id")
        if not isinstance(content_hash, str) or not isinstance(stored_figure_id, str):
            return None
        return FigureDescription(
            figure_id=stored_figure_id,
            content_hash=content_hash,
            description=record.content,
        )

    def save(
        self,
        descriptions: list[FigureDescription],
        figure_ids: list[str],
    ) -> None:
        """Persist changed descriptions and delete records for removed figures."""
        expected_ids = {self._document_id(figure_id) for figure_id in figure_ids}
        stale_ids = [
            document_id
            for document_id in self._vector_database.list_ids()
            if document_id not in expected_ids
        ]
        self._vector_database.delete(stale_ids)
        self._vector_database.upsert(
            [self._document_id(item.figure_id) for item in descriptions],
            [item.description for item in descriptions],
            [
                {
                    "source": FIGURE_SOURCE,
                    "figure_id": item.figure_id,
                    "content_hash": item.content_hash,
                }
                for item in descriptions
            ],
        )

    @staticmethod
    def _document_id(figure_id: str) -> str:
        return f"figure:{figure_id}"
