"""Shared authenticated HTTP helpers for local smoke tools."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache
def read_api_key() -> str:
    path = Path(
        os.environ.get(
            "CHAT_CLIENT_API_KEY_FILE",
            "runtime/secrets/chat_api_key",
        )
    )

    if not path.is_file():
        raise RuntimeError(
            f"Client API-key file does not exist: {path}"
        )

    value = path.read_text(
        encoding="utf-8"
    ).strip()

    if not value:
        raise RuntimeError(
            "Client API-key file is empty"
        )

    return value


def json_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": (
            "Bearer "
            + read_api_key()
        ),
    }
