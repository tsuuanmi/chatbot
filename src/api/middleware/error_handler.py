"""Consistent API error responses."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from src.common.exceptions import FrameworkError, HTTP_STATUS_CODES


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await call_next(request)
        except FrameworkError as error:
            status_code = HTTP_STATUS_CODES.get(type(error), 500)
            logger.error(
                "Framework error in {} {}: {}",
                request.method,
                request.url.path,
                error,
            )
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    }
                },
            )
        except Exception:
            logger.exception(
                "Unhandled error in {} {}", request.method, request.url.path
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "InternalServerError",
                        "message": "An unexpected error occurred",
                    }
                },
            )


def add_error_handling(app: FastAPI) -> None:
    app.add_middleware(ErrorHandlingMiddleware)
