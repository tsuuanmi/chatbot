"""Process helpers for acceptance."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import (
    AUTH_REGISTRY,
    CLIENT_API_KEY,
    COMPOSE_ENV_KEYS,
    RUNTIME_ENV,
    VERSIONS_ENV,
)


def compose_env() -> dict[str, str]:
    env = os.environ.copy()

    for key in COMPOSE_ENV_KEYS:
        env.pop(
            key,
            None,
        )

    return env


def authenticated_env() -> dict[str, str]:
    env = os.environ.copy()

    env[
        "CHAT_AUTH_REGISTRY_PATH"
    ] = AUTH_REGISTRY

    env[
        "CHAT_CLIENT_API_KEY_FILE"
    ] = CLIENT_API_KEY

    return env


def run(
    *args: str,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> None:
    print()
    print(
        "+ "
        + " ".join(args)
    )

    subprocess.run(
        args,
        env=env,
        input=input_text,
        text=(
            input_text is not None
        ),
        check=True,
    )


def compose_args(
    *args: str,
) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        RUNTIME_ENV,
        "--env-file",
        VERSIONS_ENV,
        *args,
    ]


def compose(
    *args: str,
    input_text: str | None = None,
) -> None:
    run(
        *compose_args(
            *args
        ),
        env=compose_env(),
        input_text=input_text,
    )


def require_runtime_files() -> None:
    for name in (
        VERSIONS_ENV,
        RUNTIME_ENV,
    ):
        path = Path(
            name
        )

        if not path.is_file():
            raise RuntimeError(
                f"required file is missing: {path}"
            )
