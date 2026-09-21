"""Acceptance configuration."""

from __future__ import annotations

import os


VERSIONS_ENV = os.environ.get(
    "VERSIONS_ENV",
    "versions.env",
)

RUNTIME_ENV = os.environ.get(
    "RUNTIME_ENV",
    ".env",
)

AUTH_REGISTRY = os.environ.get(
    "CHAT_AUTH_REGISTRY_PATH",
    "runtime/secrets/chat_auth.json",
)

CLIENT_API_KEY = os.environ.get(
    "CHAT_CLIENT_API_KEY_FILE",
    "runtime/secrets/chat_api_key",
)

INTERNAL_URL = os.environ.get(
    "CHAT_INTERNAL_BASE_URL",
    "http://127.0.0.1:1416",
).rstrip("/")

GATEWAY_URL = os.environ.get(
    "CHAT_GATEWAY_BASE_URL",
    "http://127.0.0.1:18080",
).rstrip("/")

COMPOSE_ENV_KEYS = (
    "CHATBOT_IMAGE",
    "HAYHOOKS_IMAGE",
    "LLAMA_CPU_IMAGE",
    "LLAMA_GPU_IMAGE",
    "LLAMA_GPU_LAYERS",
    "LLAMA_GPU_LAYERS_DRAFT",
    "LLAMA_SPEC_TYPE",
    "LLAMA_SPEC_DRAFT_N_MAX",
    "MTP_MODEL_NAME",
    "POSTGRES_IMAGE",
    "NGINX_IMAGE",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
)
