"""Offline precomputation of descriptions for configured figures."""

import asyncio
from collections.abc import Awaitable, Callable

from loguru import logger

from src.figures.models import FigureDescription
from src.figures.store import FigureDescriptionStore
from src.tools.figure_tool import FigureAsset, FigureTool

FIGURE_DESCRIPTION_PROMPT = """Phân tích hình ảnh khoa học này bằng tiếng Việt.
Nêu loại hình, nội dung chính, các trục/chú giải/nhóm dữ liệu nhìn thấy, xu hướng hoặc
mối quan hệ nổi bật và ý nghĩa khoa học có thể kết luận trực tiếp từ hình. Không suy
diễn dữ liệu, nhãn hoặc kết luận không xuất hiện trong hình. Trả lời ngắn gọn, có cấu trúc.
"""

DescriptionGenerator = Callable[[FigureAsset], Awaitable[str]]
FIGURE_SAVE_RETRIES = 3
FIGURE_SAVE_RETRY_SECONDS = 5.0


class FigureDescriptionIndexer:
    """Generate changed descriptions and remove stale figure records."""

    def __init__(
        self,
        figure_tool: FigureTool,
        store: FigureDescriptionStore,
        generate: DescriptionGenerator,
    ) -> None:
        self._figure_tool = figure_tool
        self._store = store
        self._generate = generate

    async def index(self) -> int:
        generated_count = 0
        indexed = 0
        figure_ids = self._figure_tool.list_figures()
        total_figures = len(figure_ids)
        logger.info("Starting figure indexing for {} configured figures", total_figures)
        for position, figure_id in enumerate(figure_ids, start=1):
            logger.info("Figure {}/{}: loading {}", position, total_figures, figure_id)
            asset = await asyncio.to_thread(self._figure_tool.load, figure_id)
            if asset is None:
                raise RuntimeError(f"Configured figure disappeared: {figure_id}")

            existing = await asyncio.to_thread(self._store.get, figure_id)
            if existing and existing.content_hash == asset.content_hash:
                indexed += 1
                logger.info(
                    "Figure {}/{}: reused stored description for {}",
                    position,
                    total_figures,
                    figure_id,
                )
                continue

            logger.info(
                "Figure {}/{}: generating description for {}",
                position,
                total_figures,
                figure_id,
            )
            description = (await self._generate(asset)).strip()
            if not description:
                raise RuntimeError(f"Empty description generated for {figure_id}")
            logger.info(
                "Figure {}/{}: generated description for {}",
                position,
                total_figures,
                figure_id,
            )
            generated_description = FigureDescription(
                figure_id=figure_id,
                content_hash=asset.content_hash,
                description=description,
            )
            await self._save_with_retry(
                [generated_description],
                figure_ids,
                figure_id,
            )
            generated_count += 1
            indexed += 1
            logger.info(
                "Figure {}/{}: stored description for {}",
                position,
                total_figures,
                figure_id,
            )

        await self._save_with_retry([], figure_ids, "stale-record cleanup")
        logger.info(
            "Indexed {} figure descriptions ({} generated)",
            indexed,
            generated_count,
        )
        return indexed

    async def _save_with_retry(
        self,
        descriptions: list[FigureDescription],
        figure_ids: list[str],
        operation: str,
    ) -> None:
        total_attempts = FIGURE_SAVE_RETRIES + 1
        for attempt in range(1, total_attempts + 1):
            try:
                await asyncio.to_thread(self._store.save, descriptions, figure_ids)
                return
            except Exception as error:
                if attempt == total_attempts:
                    logger.exception(
                        "Figure storage failed after {} retries: {}",
                        FIGURE_SAVE_RETRIES,
                        operation,
                    )
                    raise
                logger.warning(
                    "Figure storage attempt {}/{} failed for {} ({}); retrying",
                    attempt,
                    total_attempts,
                    operation,
                    type(error).__name__,
                )
                await asyncio.sleep(FIGURE_SAVE_RETRY_SECONDS)
