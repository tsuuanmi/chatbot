"""Bearer API-key authentication for trusted LAN clients."""

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from src.config.settings import get_settings

_CLIENT_ID_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{1,63}")
_TOKEN_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class AuthenticatedClient:
    client_id: str


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _load_key_hashes(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("unsupported API-key file format")
        if payload.get("version") != 1 or not isinstance(payload.get("clients"), list):
            raise ValueError("unsupported API-key file format")
        clients: dict[str, str] = {}
        for item in payload["clients"]:
            if not isinstance(item, dict):
                raise ValueError("invalid API client entry")
            client_id = item.get("id")
            token_hash_value = item.get("token_sha256")
            if not isinstance(client_id, str) or not isinstance(token_hash_value, str):
                raise ValueError("invalid API client entry")
            token_hash = token_hash_value.casefold()
            if not _CLIENT_ID_PATTERN.fullmatch(client_id):
                raise ValueError("invalid client identifier")
            if not _TOKEN_HASH_PATTERN.fullmatch(token_hash):
                raise ValueError("invalid API-key hash")
            if client_id in clients:
                raise ValueError("duplicate client identifier")
            clients[client_id] = token_hash
        if not clients:
            raise ValueError("no API clients are configured")
        return clients
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("API authentication is not configured") from error


def healthcheck_authentication() -> None:
    """Validate the configured API-key file when authentication is enabled."""
    settings = get_settings()
    if settings.api_auth_enabled:
        _load_key_hashes(Path(settings.api_keys_file))


async def require_client(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> AuthenticatedClient:
    """Authenticate one client without retaining its plaintext key."""
    settings = get_settings()
    if not settings.api_auth_enabled:
        return AuthenticatedClient(client_id="local-development")
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        key_hashes = _load_key_hashes(Path(settings.api_keys_file))
    except RuntimeError:
        logger.exception("API authentication configuration could not be loaded")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is unavailable",
        ) from None

    candidate = hash_api_key(credentials.credentials)
    for client_id, expected in key_hashes.items():
        if secrets.compare_digest(candidate, expected):
            return AuthenticatedClient(client_id=client_id)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key",
        headers={"WWW-Authenticate": "Bearer"},
    )
