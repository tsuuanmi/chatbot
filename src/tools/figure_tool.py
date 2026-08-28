"""Safe access to configured figure assets."""

import base64
import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from loguru import logger
from PIL import Image

from src.config.settings import get_settings

_ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True, slots=True)
class FigureAsset:
    figure_id: str
    content_hash: str
    base64_image: str
    mime_type: str
    width: int
    height: int


class FigureTool:
    """Load configured figure files without allowing arbitrary paths."""

    def __init__(self, figures_dir: str | None = None) -> None:
        self._figures_dir = Path(figures_dir or get_settings().figures_dir)
        logger.info("Figure tool initialized: {}", self._figures_dir)

    def load(
        self, figure_id: str, max_size: tuple[int, int] = (1024, 1024)
    ) -> FigureAsset | None:
        path = self._find_file(figure_id)
        if path is None:
            return None

        source_bytes = path.read_bytes()
        with Image.open(BytesIO(source_bytes)) as source:
            image = source.convert("RGB")
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(output, format="PNG")
        return FigureAsset(
            figure_id=path.stem,
            content_hash=hashlib.sha256(source_bytes).hexdigest(),
            base64_image=base64.b64encode(output.getvalue()).decode(),
            mime_type="image/png",
            width=image.width,
            height=image.height,
        )

    def list_figures(self) -> list[str]:
        if not self._figures_dir.exists():
            return []
        return sorted(
            path.stem
            for path in self._figures_dir.iterdir()
            if path.is_file() and path.suffix.lower() in _ALLOWED_EXTENSIONS
        )

    def _find_file(self, figure_id: str) -> Path | None:
        safe_id = re.sub(r"\.(png|jpg|jpeg|webp)$", "", figure_id, flags=re.IGNORECASE)
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", safe_id):
            return None
        for extension in _ALLOWED_EXTENSIONS:
            path = self._figures_dir / f"{safe_id}{extension}"
            if path.is_file():
                return path
        return None
