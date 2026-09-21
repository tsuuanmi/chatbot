"""Shared PostgreSQL connection configuration."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value


def read_secret(path_env: str) -> str:
    path = Path(required_env(path_env))

    if not path.is_file():
        raise RuntimeError(
            f"Secret file does not exist: {path}"
        )

    value = path.read_text(
        encoding="utf-8"
    ).strip()

    if not value:
        raise RuntimeError(
            f"Secret file is empty: {path}"
        )

    return value


def postgres_connection_string() -> str:
    host = required_env("POSTGRES_HOST")
    port = required_env("POSTGRES_PORT")
    database = required_env("POSTGRES_DB")
    user = required_env("POSTGRES_USER")
    password = read_secret(
        "POSTGRES_PASSWORD_FILE"
    )

    return (
        "postgresql://"
        f"{quote(user, safe='')}:"
        f"{quote(password, safe='')}"
        f"@{host}:{port}/"
        f"{quote(database, safe='')}"
    )
