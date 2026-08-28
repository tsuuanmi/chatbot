"""Application dependency container and resource ownership."""

from dataclasses import dataclass

from loguru import logger

from src.base.components.embeddings import LlamaCppEmbedding, create_embedding
from src.base.components.vector_databases import (
    BaseVectorDatabase,
    create_vector_database,
)
from src.config.settings import Settings, get_settings
from src.domain.classifier import DomainClassifier
from src.figures.store import FigureDescriptionStore
from src.knowledge.retriever import KnowledgeRetriever
from src.tools.figure_tool import FigureTool


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: Settings
    embedding: LlamaCppEmbedding
    vector_database: BaseVectorDatabase
    figure_tool: FigureTool
    figure_descriptions: FigureDescriptionStore
    domain_classifier: DomainClassifier
    knowledge_retriever: KnowledgeRetriever

    def close(self) -> None:
        self.embedding.close()


_container: ApplicationContainer | None = None


def setup_container() -> ApplicationContainer:
    global _container
    if _container is None:
        settings = get_settings()
        embedding = create_embedding(settings)
        vector_database = create_vector_database(
            embedding, collection_name=settings.chroma_collection_name
        )
        figure_database = create_vector_database(
            embedding, collection_name=settings.chroma_figure_collection_name
        )
        _container = ApplicationContainer(
            settings=settings,
            embedding=embedding,
            vector_database=vector_database,
            figure_tool=FigureTool(settings.figures_dir),
            figure_descriptions=FigureDescriptionStore(figure_database),
            domain_classifier=DomainClassifier(
                embedding,
                minimum_confidence=settings.domain_min_confidence,
                minimum_margin=settings.domain_min_margin,
                high_risk_threshold=settings.domain_high_risk_threshold,
            ),
            knowledge_retriever=KnowledgeRetriever(
                vector_database,
                top_k=settings.rag_top_k,
                max_distance=settings.rag_max_distance,
            ),
        )
        logger.info("Application dependencies initialized")
    return _container


def get_container() -> ApplicationContainer:
    return setup_container()


def close_container() -> None:
    global _container
    if _container is not None:
        _container.close()
        _container = None
