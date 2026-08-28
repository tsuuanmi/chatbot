"""API v1 route aggregation."""

from fastapi import APIRouter

from src.api.v1 import chat, health

router = APIRouter()
router.include_router(health.router)
router.include_router(chat.router)
