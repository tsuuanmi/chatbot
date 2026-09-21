"""Offline API-key authentication and request identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


_OWNER_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)

_DIGEST_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)

_MIN_API_KEY_LENGTH = 32
_MAX_API_KEY_LENGTH = 512
_MAX_IDENTITIES = 1000
_MAX_REGISTRY_BYTES = 256 * 1024


class AuthConfigError(RuntimeError):
    """Raised when the authentication registry is invalid."""


class AuthenticationContextError(RuntimeError):
    """Raised when authenticated identity is unavailable."""


@dataclass(frozen=True, slots=True)
class AuthIdentity:
    owner_id: str


@dataclass(frozen=True, slots=True)
class _Credential:
    identity: AuthIdentity
    digest: bytes


class AuthRegistry:
    """Immutable timing-safe API-key identity registry."""

    def __init__(
        self,
        credentials: tuple[_Credential, ...],
    ) -> None:
        if not credentials:
            raise AuthConfigError(
                "Authentication registry must contain at least one identity"
            )

        self._credentials = credentials

    @classmethod
    def from_file(
        cls,
        path: Path,
    ) -> "AuthRegistry":
        if not path.is_file():
            raise AuthConfigError(
                f"Authentication registry does not exist: {path}"
            )

        try:
            size = path.stat().st_size
        except OSError as error:
            raise AuthConfigError(
                "Unable to stat authentication registry"
            ) from error

        if size > _MAX_REGISTRY_BYTES:
            raise AuthConfigError(
                "Authentication registry exceeds size limit"
            )

        try:
            content = path.read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as error:
            raise AuthConfigError(
                "Unable to read authentication registry"
            ) from error

        try:
            raw = json.loads(
                content
            )
        except json.JSONDecodeError as error:
            raise AuthConfigError(
                "Authentication registry is not valid JSON"
            ) from error

        if not isinstance(raw, dict):
            raise AuthConfigError(
                "Authentication registry root must be an object"
            )

        if raw.get("version") != 1:
            raise AuthConfigError(
                "Unsupported authentication registry version"
            )

        identities = raw.get(
            "identities"
        )

        if (
            not isinstance(identities, list)
            or not identities
        ):
            raise AuthConfigError(
                "Authentication registry identities must be a non-empty list"
            )

        if len(identities) > _MAX_IDENTITIES:
            raise AuthConfigError(
                "Authentication registry contains too many identities"
            )

        owner_ids: set[str] = set()
        digests: set[bytes] = set()
        credentials: list[_Credential] = []

        for index, item in enumerate(
            identities
        ):
            if not isinstance(item, dict):
                raise AuthConfigError(
                    f"Identity {index} must be an object"
                )

            raw_owner_id = item.get(
                "owner_id"
            )

            raw_digest = item.get(
                "api_key_sha256"
            )

            if not isinstance(
                raw_owner_id,
                str,
            ):
                raise AuthConfigError(
                    f"owner_id at identity {index} must be a string"
                )

            if not isinstance(
                raw_digest,
                str,
            ):
                raise AuthConfigError(
                    f"api_key_sha256 at identity {index} must be a string"
                )

            owner_id = raw_owner_id.strip()
            digest_hex = (
                raw_digest.strip().lower()
            )

            if not _OWNER_PATTERN.fullmatch(
                owner_id
            ):
                raise AuthConfigError(
                    f"Invalid owner_id at identity {index}"
                )

            if not _DIGEST_PATTERN.fullmatch(
                digest_hex
            ):
                raise AuthConfigError(
                    f"Invalid API-key digest at identity {index}"
                )

            digest = bytes.fromhex(
                digest_hex
            )

            if owner_id in owner_ids:
                raise AuthConfigError(
                    f"Duplicate owner_id: {owner_id}"
                )

            if digest in digests:
                raise AuthConfigError(
                    "Duplicate API-key digest"
                )

            owner_ids.add(
                owner_id
            )
            digests.add(
                digest
            )

            credentials.append(
                _Credential(
                    identity=AuthIdentity(
                        owner_id=owner_id
                    ),
                    digest=digest,
                )
            )

        return cls(
            tuple(credentials)
        )

    def authenticate(
        self,
        api_key: str,
    ) -> AuthIdentity | None:
        if (
            api_key != api_key.strip()
            or not (
                _MIN_API_KEY_LENGTH
                <= len(api_key)
                <= _MAX_API_KEY_LENGTH
            )
        ):
            return None

        candidate = hashlib.sha256(
            api_key.encode("utf-8")
        ).digest()

        matched: AuthIdentity | None = None

        # Check every configured digest rather than returning early.
        for credential in self._credentials:
            if secrets.compare_digest(
                candidate,
                credential.digest,
            ):
                matched = credential.identity

        return matched


_current_identity: ContextVar[
    AuthIdentity | None
] = ContextVar(
    "chat_authenticated_identity",
    default=None,
)


@contextmanager
def identity_scope(
    identity: AuthIdentity,
) -> Iterator[None]:
    token = _current_identity.set(
        identity
    )

    try:
        yield
    finally:
        _current_identity.reset(
            token
        )


def current_identity() -> AuthIdentity:
    identity = _current_identity.get()

    if identity is None:
        raise AuthenticationContextError(
            "Authenticated identity is unavailable"
        )

    return identity


@lru_cache
def get_auth_registry() -> AuthRegistry:
    path_value = os.environ.get(
        "CHAT_AUTH_FILE",
        "",
    ).strip()

    if not path_value:
        raise AuthConfigError(
            "CHAT_AUTH_FILE is required"
        )

    return AuthRegistry.from_file(
        Path(path_value)
    )
