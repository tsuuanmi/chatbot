"""ASGI application entry point."""

import uvicorn
from loguru import logger

from src.api import create_app
from src.config.settings import get_settings

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    logger.info("Starting API on {}:{}", settings.api_host, settings.api_port)
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
