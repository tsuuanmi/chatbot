from src.base.components.embeddings.base import BaseEmbedding
from src.base.components.vector_databases.base import BaseVectorDatabase
from src.base.components.vector_databases.chromadb import ChromaVectorDatabase


def create_vector_database(
    embedding: BaseEmbedding,
    collection_name: str = "default",
) -> BaseVectorDatabase:
    return ChromaVectorDatabase(embedding=embedding, collection_name=collection_name)


__all__ = ["BaseVectorDatabase", "create_vector_database"]
