"""Build the project knowledge and figure-description database."""

import asyncio
from pathlib import Path

from loguru import logger

from src.container import close_container, setup_container
from src.figures import FIGURE_DESCRIPTION_PROMPT, FigureDescriptionIndexer
from src.knowledge.indexer import KnowledgeIndexer
from src.llm.client import close_llm_client, get_llm_client


async def index_documents(
    directory: Path = Path("data/documents"),
    *,
    index_figures: bool = True,
) -> int:
    container = setup_container()
    indexer = KnowledgeIndexer(container.vector_database)
    total = 0

    knowledge_base = directory / "knowledge_base.tsv"
    if knowledge_base.is_file():
        total += await indexer.index_knowledge_base(knowledge_base)

    total += await indexer.index_directory(directory)

    if index_figures:
        figure_indexer = FigureDescriptionIndexer(
            container.figure_tool,
            container.figure_descriptions,
            lambda asset: get_llm_client().describe_figure(
                asset, FIGURE_DESCRIPTION_PROMPT
            ),
        )
        total += await figure_indexer.index()

    logger.info("Indexed {} knowledge and figure records", total)
    return total


async def main() -> None:
    try:
        await index_documents()
    finally:
        await close_llm_client()
        close_container()


if __name__ == "__main__":
    asyncio.run(main())
