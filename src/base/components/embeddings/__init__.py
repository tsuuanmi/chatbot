"""Embedding component exports."""

from src.base.components.embeddings.base import BaseEmbedding
from src.base.components.embeddings.llamacpp import LlamaCppEmbedding
from src.config.settings import Settings


def create_embedding(settings: Settings) -> LlamaCppEmbedding:
    return LlamaCppEmbedding(settings)


__all__ = ["BaseEmbedding", "LlamaCppEmbedding", "create_embedding"]
