"""Runtime secret and Compose security checks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .proc import (
    compose_args,
    compose_env,
)

def secret_group_check() -> None:
    services = (
        "postgres",
        "db-migrate",
        "index-knowledge",
        "llama-server",
        "chatbot",
    )

    for service in services:
        result = subprocess.run(
            compose_args(
                "config",
                service,
            ),
            env=compose_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )

        if (
            "group_add:"
            not in result.stdout
        ):
            raise RuntimeError(
                f"{service} is missing "
                "group_add"
            )

        print(
            f"PASS secret group {service}"
        )

    print(
        "SECRET GROUP CONFIG PASS"
    )


def secret_audit() -> None:
    secret_files = (
        Path(
            "runtime/secrets/chat_api_key"
        ),
        Path(
            "runtime/secrets/"
            "chat_api_key_owner_b"
        ),
        Path(
            "runtime/secrets/llama_api_key"
        ),
        Path(
            "runtime/secrets/"
            "postgres_password"
        ),
    )

    tracked = subprocess.run(
        [
            "git",
            "ls-files",
            "runtime/secrets",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    ).stdout.strip()

    if tracked:
        raise RuntimeError(
            "runtime secret files are "
            "tracked by git"
        )

    values: list[str] = []

    for relative in secret_files:
        path = relative

        if not path.is_file():
            continue

        value = path.read_text(
            encoding="utf-8"
        ).strip()

        if value:
            values.append(
                value
            )

    registry = Path(
        "runtime/secrets/chat_auth.json"
    )

    if registry.is_file():
        data = json.loads(
            registry.read_text(
                encoding="utf-8"
            )
        )

        for identity in data.get(
            "identities",
            [],
        ):
            if not isinstance(
                identity,
                dict,
            ):
                continue

            digest = identity.get(
                "api_key_sha256"
            )

            if (
                isinstance(
                    digest,
                    str,
                )
                and digest
            ):
                values.append(
                    digest
                )

    logs = subprocess.run(
        compose_args(
            "logs",
            "--no-color",
            "chatbot",
            "proxy",
        ),
        env=compose_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    ).stdout

    for value in values:
        if value in logs:
            raise RuntimeError(
                "raw secret detected "
                "in runtime logs"
            )

    print(
        "PASS runtime secrets are not tracked"
    )

    print(
        "PASS raw secrets absent "
        "from chatbot/proxy logs"
    )

    print(
        "SECRET AUDIT PASS"
    )
