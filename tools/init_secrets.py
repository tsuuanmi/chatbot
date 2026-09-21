"""Initialize local runtime secrets for a development checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from pathlib import Path


OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)

SECRET_NAMES = (
    "chat_auth.json",
    "chat_api_key",
    "llama_api_key",
    "postgres_password",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.is_file():
        raise RuntimeError(
            f"missing environment file: {path}"
        )

    for raw in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)

        values[key.strip()] = (
            value.strip()
            .strip('"')
            .strip("'")
        )

    return values


def write_exclusive(
    path: Path,
    content: str,
) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL,
        0o600,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    except Exception:
        path.unlink(missing_ok=True)
        raise


def require_existing_secret(
    path: Path,
) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
    ):
        raise RuntimeError(
            f"invalid runtime secret: {path}"
        )

    if not path.read_text(
        encoding="utf-8"
    ).strip():
        raise RuntimeError(
            f"empty runtime secret: {path}"
        )


def main() -> None:
    root = (
        Path(__file__)
        .resolve()
        .parent
        .parent
    )

    env = load_env(
        root / ".env"
    )

    runtime_dir = Path(
        env.get(
            "CHATBOT_RUNTIME_DIR",
            "./runtime",
        )
    )

    if not runtime_dir.is_absolute():
        runtime_dir = (
            root / runtime_dir
        )

    secrets_dir = (
        runtime_dir / "secrets"
    )

    secrets_dir.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    secrets_dir.chmod(0o700)

    paths = {
        name: secrets_dir / name
        for name in SECRET_NAMES
    }

    existing = [
        name
        for name, path in paths.items()
        if path.exists()
    ]

    if existing:
        if len(existing) != len(paths):
            missing = sorted(
                set(paths) - set(existing)
            )

            raise RuntimeError(
                "partial runtime secret state; "
                f"existing={sorted(existing)} "
                f"missing={missing}"
            )

        for path in paths.values():
            require_existing_secret(path)

        print(
            "RUNTIME SECRETS ALREADY EXIST"
        )
        return

    owner = env.get(
        "CHAT_OWNER_ID",
        "local-development",
    ).strip()

    if not OWNER_PATTERN.fullmatch(
        owner
    ):
        raise RuntimeError(
            f"invalid CHAT_OWNER_ID: "
            f"{owner!r}"
        )

    client_key = (
        secrets.token_urlsafe(32)
    )

    llama_key = (
        secrets.token_urlsafe(32)
    )

    postgres_password = (
        secrets.token_urlsafe(32)
    )

    registry = {
        "version": 1,
        "identities": [
            {
                "owner_id": owner,
                "api_key_sha256": (
                    hashlib.sha256(
                        client_key.encode(
                            "utf-8"
                        )
                    ).hexdigest()
                ),
            }
        ],
    }

    contents = {
        "chat_auth.json": (
            json.dumps(
                registry,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        "chat_api_key": (
            client_key + "\n"
        ),
        "llama_api_key": (
            llama_key + "\n"
        ),
        "postgres_password": (
            postgres_password + "\n"
        ),
    }

    created: list[Path] = []

    try:
        for name in SECRET_NAMES:
            path = paths[name]

            write_exclusive(
                path,
                contents[name],
            )

            created.append(path)

        secret_gid = int(
            env.get(
                "CHATBOT_SECRET_GID",
                str(os.getgid()),
            )
        )

        for name in (
            "chat_auth.json",
            "llama_api_key",
            "postgres_password",
        ):
            os.chown(
                paths[name],
                -1,
                secret_gid,
            )

            paths[name].chmod(
                0o640
            )

        paths[
            "chat_api_key"
        ].chmod(0o600)

    except Exception:
        for path in created:
            path.unlink(
                missing_ok=True
            )
        raise

    print(
        "RUNTIME SECRETS CREATED "
        f"owner_id={owner}"
    )


if __name__ == "__main__":
    main()
