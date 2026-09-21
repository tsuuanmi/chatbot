"""Authenticated programmatic Hayhooks application."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from hayhooks import (
    create_app,
    run_app,
)
from hayhooks.settings import settings
from pydantic import BaseModel

from chatbot_app.auth import (
    current_identity,
    get_auth_registry,
    identity_scope,
)
from chatbot_app.forensic_chat import (
    get_forensic_chat,
)
from chatbot_app.public_api import (
    router as public_api_router,
)


logger = logging.getLogger(__name__)


class StreamChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None
    figure_id: str | None = None
    image: str | None = None


_PUBLIC_PATHS = {
    "/live",
    "/status",
    "/healthcheck/run",
}

_BLOCKED_EXACT_PATHS = {
    "/deploy-yaml",
    "/deploy_files",
}


def _normalize(
    path: str,
) -> str:
    path = (
        f"/{path.lstrip('/')}"
        if path
        else "/"
    )

    return (
        path.rstrip("/")
        or "/"
    )


def _relative_path(
    path: str,
    root_path: str,
) -> str:
    candidate = _normalize(
        path
    )

    root = _normalize(
        root_path
    )

    if root != "/":
        if candidate == root:
            return "/"

        if candidate.startswith(
            f"{root}/"
        ):
            candidate = candidate[
                len(root):
            ]

    return _normalize(
        candidate
    )


def _blocked_management_path(
    path: str,
) -> bool:
    return (
        path in _BLOCKED_EXACT_PATHS
        or path.startswith(
            "/undeploy/"
        )
    )


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "detail": "Unauthorized",
        },
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )


def create_authenticated_app():
    registry = get_auth_registry()
    app = create_app()
    app.include_router(
        public_api_router
    )

    @app.get("/live")
    async def live() -> dict[str, str]:
        return {
            "status": "ok",
        }

    @app.middleware("http")
    async def authentication_middleware(
        request: Request,
        call_next,
    ):
        path = _relative_path(
            request.url.path,
            settings.root_path,
        )

        # Browser CORS preflight must reach CORSMiddleware.
        if request.method == "OPTIONS":
            return await call_next(
                request
            )

        if path in _PUBLIC_PATHS:
            return await call_next(
                request
            )

        # Production pipelines are deployed only at startup.
        # Runtime mutation routes are intentionally unavailable.
        if _blocked_management_path(
            path
        ):
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "Not Found",
                },
            )

        authorization = request.headers.get(
            "Authorization",
            "",
        )

        parts = authorization.split()

        if (
            len(parts) != 2
            or parts[0].lower()
            != "bearer"
        ):
            return _unauthorized()

        identity = registry.authenticate(
            parts[1]
        )

        if identity is None:
            return _unauthorized()

        with identity_scope(
            identity
        ):
            return await call_next(
                request
            )

    @app.post(
        "/chat/stream",
        response_model=None,
    )
    async def stream_chat(
        payload: StreamChatRequest,
    ) -> StreamingResponse:
        identity = current_identity()
        chat = get_forensic_chat()

        async def events():
            try:
                with identity_scope(identity):
                    async for event in chat.stream_answer(
                        payload.message,
                        (
                            str(payload.conversation_id)
                            if payload.conversation_id
                            is not None
                            else None
                        ),
                        figure_id=payload.figure_id,
                        image=payload.image,
                    ):
                        yield (
                            "data: "
                            + json.dumps(
                                event,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            + "\n\n"
                        )

            except asyncio.CancelledError:
                raise

            except Exception:
                logger.exception(
                    "Chat stream failed"
                )

                yield (
                    'data: {"type":"error",'
                    '"error":"An unexpected error occurred"}'
                    "\n\n"
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


hayhooks = create_authenticated_app()


if __name__ == "__main__":
    run_app(
        hayhooks
    )
