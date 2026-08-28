"""Precomputed figure descriptions."""

from src.figures.indexer import FIGURE_DESCRIPTION_PROMPT, FigureDescriptionIndexer
from src.figures.models import FigureDescription
from src.figures.store import FigureDescriptionStore

__all__ = [
    "FIGURE_DESCRIPTION_PROMPT",
    "FigureDescription",
    "FigureDescriptionIndexer",
    "FigureDescriptionStore",
]
