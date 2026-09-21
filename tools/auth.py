"""Canonical local authentication maintenance CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

from chatbot_app.auth import AuthRegistry


DEFAULT_OWNER_ID = "local-development"

OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)


def registry_path() -> Path:
    return Path(
        os.environ.get(
            "CHAT_AUTH_REGISTRY_PATH",
            "runtime/secrets/chat_auth.json",
        )
    )


def client_key_path() -> Path:
    return Path(
        os.environ.get(
            "CHAT_CLIENT_API_KEY_FILE",
            "runtime/secrets/chat_api_key",
        )
    )


def require_owner(
    owner: str,
) -> str:
    owner = owner.strip()

    if not OWNER_PATTERN.fullmatch(
        owner
    ):
        raise RuntimeError(
            "invalid owner id"
        )

    return owner


def write_private(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    path.parent.chmod(
        0o700
    )

    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )

    temporary_path = Path(
        temporary
    )

    try:
        os.fchmod(
            descriptor,
            0o600,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                content
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        temporary_path.unlink(
            missing_ok=True
        )


def write_exclusive(
    path: Path,
    content: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    path.parent.chmod(
        0o700
    )

    descriptor = os.open(
        path,
        (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        ),
        0o600,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                content
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

    except Exception:
        path.unlink(
            missing_ok=True
        )
        raise


def require_private_file(
    path: Path,
    *,
    label: str,
    allowed_modes: set[int],
) -> None:
    if not path.is_file():
        raise RuntimeError(
            f"missing {label}: {path}"
        )

    if path.is_symlink():
        raise RuntimeError(
            f"{label} must not be a symbolic link"
        )

    mode = stat.S_IMODE(
        path.stat().st_mode
    )

    if mode not in allowed_modes:
        expected = "/".join(
            f"{value:04o}"
            for value in sorted(
                allowed_modes
            )
        )

        raise RuntimeError(
            f"{label} permissions are invalid: "
            f"{mode:04o}; expected {expected}"
        )


def check() -> None:
    registry = registry_path()
    client_key = client_key_path()

    require_private_file(
        registry,
        label="auth registry",
        allowed_modes={
            0o400,
            0o440,
            0o600,
            0o640,
        },
    )

    require_private_file(
        client_key,
        label="client API key",
        allowed_modes={
            0o400,
            0o600,
        },
    )

    auth_registry = AuthRegistry.from_file(
        registry
    )

    api_key = client_key.read_text(
        encoding="utf-8"
    ).strip()

    if not api_key:
        raise RuntimeError(
            "client API key is empty"
        )

    identity = auth_registry.authenticate(
        api_key
    )

    if identity is None:
        raise RuntimeError(
            "client API key does not match "
            "authentication registry"
        )

    print(
        f"AUTH CONFIG PASS "
        f"owner_id={identity.owner_id}"
    )


def init(
    owner: str,
) -> None:
    owner = require_owner(
        owner
    )

    registry = registry_path()
    client_key = client_key_path()

    registry_exists = (
        registry.exists()
    )

    key_exists = (
        client_key.exists()
    )

    if registry_exists or key_exists:
        if not (
            registry_exists
            and key_exists
        ):
            raise RuntimeError(
                "auth secret state is incomplete; "
                "registry and client key must both exist"
            )

        check()

        print(
            "AUTH SECRETS ALREADY EXIST"
        )
        return

    api_key = secrets.token_urlsafe(
        32
    )

    digest = hashlib.sha256(
        api_key.encode(
            "utf-8"
        )
    ).hexdigest()

    data = {
        "version": 1,
        "identities": [
            {
                "owner_id": owner,
                "api_key_sha256": digest,
            }
        ],
    }

    created: list[Path] = []

    try:
        write_exclusive(
            registry,
            json.dumps(
                data,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        created.append(
            registry
        )

        write_exclusive(
            client_key,
            api_key + "\n",
        )

        created.append(
            client_key
        )

    except Exception:
        for path in created:
            path.unlink(
                missing_ok=True
            )

        raise

    check()

    print(
        "AUTH SECRETS CREATED"
    )


def rotate(
    owner: str,
    key_file: Path,
) -> None:
    owner = require_owner(
        owner
    )

    registry = registry_path()

    if not key_file.is_file():
        raise RuntimeError(
            "client key file does not exist"
        )

    current_key = key_file.read_text(
        encoding="utf-8"
    ).strip()

    if not current_key:
        raise RuntimeError(
            "client key file is empty"
        )

    auth_registry = AuthRegistry.from_file(
        registry
    )

    current_identity = (
        auth_registry.authenticate(
            current_key
        )
    )

    if (
        current_identity is None
        or current_identity.owner_id
        != owner
    ):
        raise RuntimeError(
            "client key file does not belong "
            "to requested owner"
        )

    original_registry = (
        registry.read_text(
            encoding="utf-8"
        )
    )

    original_key = (
        current_key + "\n"
    )

    data = json.loads(
        original_registry
    )

    identities = data.get(
        "identities"
    )

    if not isinstance(
        identities,
        list,
    ):
        raise RuntimeError(
            "invalid authentication registry"
        )

    matching = [
        item
        for item in identities
        if (
            isinstance(
                item,
                dict,
            )
            and item.get(
                "owner_id"
            )
            == owner
        )
    ]

    if len(matching) != 1:
        raise RuntimeError(
            "owner must exist exactly once"
        )

    new_key = secrets.token_urlsafe(
        32
    )

    matching[0][
        "api_key_sha256"
    ] = hashlib.sha256(
        new_key.encode(
            "utf-8"
        )
    ).hexdigest()

    new_registry = (
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    try:
        write_private(
            key_file,
            new_key + "\n",
        )

        write_private(
            registry,
            new_registry,
        )

        final_registry = (
            AuthRegistry.from_file(
                registry
            )
        )

        identity = (
            final_registry.authenticate(
                new_key
            )
        )

        if (
            identity is None
            or identity.owner_id
            != owner
        ):
            raise RuntimeError(
                "rotated credential "
                "validation failed"
            )

    except Exception as error:
        rollback_errors: list[str] = []

        try:
            write_private(
                registry,
                original_registry,
            )
        except Exception as rollback:
            rollback_errors.append(
                f"registry: {rollback}"
            )

        try:
            write_private(
                key_file,
                original_key,
            )
        except Exception as rollback:
            rollback_errors.append(
                f"key: {rollback}"
            )

        if rollback_errors:
            raise RuntimeError(
                "credential rotation failed "
                "and rollback was incomplete: "
                + "; ".join(
                    rollback_errors
                )
            ) from error

        raise

    print(
        f"AUTH ROTATION PASS "
        f"owner_id={owner}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    init_parser = commands.add_parser(
        "init"
    )

    init_parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER_ID,
    )

    commands.add_parser(
        "check"
    )

    rotate_parser = commands.add_parser(
        "rotate"
    )

    rotate_parser.add_argument(
        "--owner",
        required=True,
    )

    rotate_parser.add_argument(
        "--key-file",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "init":
        init(
            args.owner
        )
        return

    if args.command == "check":
        check()
        return

    if args.command == "rotate":
        rotate(
            args.owner,
            args.key_file,
        )
        return

    raise RuntimeError(
        f"unsupported command: "
        f"{args.command}"
    )


if __name__ == "__main__":
    main()
