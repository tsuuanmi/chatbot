"""FastAPI application factory and resource lifecycle."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api.middleware.error_handler import add_error_handling
from src.api.v1 import router as v1_router
from src.config.settings import get_settings
from src.container import close_container, setup_container
from src.database.history_service import get_history_service
from src.llm.client import close_llm_client
from src.readiness import warmup_application


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting chatbot application")
    container = setup_container()
    history = get_history_service()
    try:
        await warmup_application(container, history)
        yield
    finally:
        await get_history_service().close()
        await close_llm_client()
        close_container()
        logger.info("Chatbot application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Chatbot BCA API",
        description="Offline Gemma forensic-genetics chatbot API",
        lifespan=lifespan,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    add_error_handling(app)
    app.include_router(v1_router, prefix="/api/v1")
    return app
