"""API contract tests."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.api.auth import hash_api_key, require_client


def _events(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.asyncio
async def test_api_key_authentication_accepts_only_configured_client(tmp_path) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text(
        json.dumps(
            {
                "version": 1,
                "clients": [
                    {"id": "postman-one", "token_sha256": hash_api_key("secret")}
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = SimpleNamespace(api_auth_enabled=True, api_keys_file=str(key_file))

    with patch("src.api.auth.get_settings", return_value=settings):
        client = await require_client(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
        )
        assert client.client_id == "postman-one"
        with pytest.raises(HTTPException) as denied:
            await require_client(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
            )
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_api_key_configuration_failure_is_service_unavailable(tmp_path) -> None:
    settings = SimpleNamespace(
        api_auth_enabled=True,
        api_keys_file=str(tmp_path / "missing-api-keys.json"),
    )
    with (
        patch("src.api.auth.get_settings", return_value=settings),
        pytest.raises(HTTPException) as unavailable,
    ):
        await require_client(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
        )

    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {"version": 1, "clients": [{"id": 7}]}])
async def test_malformed_api_key_configuration_is_service_unavailable(
    tmp_path, payload
) -> None:
    key_file = tmp_path / "api_keys.json"
    key_file.write_text(json.dumps(payload), encoding="utf-8")
    settings = SimpleNamespace(api_auth_enabled=True, api_keys_file=str(key_file))
    with (
        patch("src.api.auth.get_settings", return_value=settings),
        pytest.raises(HTTPException) as unavailable,
    ):
        await require_client(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
        )

    assert unavailable.value.status_code == 503


def test_health(client) -> None:
    test_client, _ = client
    assert test_client.get("/api/v1/health").json() == {"status": "healthy"}


def test_chat_returns_explicit_source_and_persists(client) -> None:
    test_client, history = client
    response = test_client.post(
        "/api/v1/chat", json={"conversation_id": "test", "query": "What is STR?"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "response": "Test answer",
        "conversation_id": "test",
        "source": "generated",
        "conversation_status": "active",
        "citations": [],
    }
    from src.domain.models import DomainLabel, RiskLevel

    history.save_turn.assert_awaited_once_with(
        "test",
        "What is STR?",
        "Test answer",
        DomainLabel.IN_DOMAIN,
        RiskLevel.STANDARD,
        owner_id="local-development",
    )


def test_chat_denies_conversation_owned_by_another_client(client) -> None:
    test_client, history = client
    history.claim_conversation.return_value = False

    response = test_client.post(
        "/api/v1/chat",
        json={"conversation_id": "owned", "query": "What is STR?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}


def test_chat_generates_conversation_id(client) -> None:
    test_client, _ = client
    payload = test_client.post("/api/v1/chat", json={"query": "What is STR?"}).json()
    assert payload["conversation_id"]


def test_chat_rejects_missing_or_blank_query(client) -> None:
    test_client, _ = client
    assert test_client.post("/api/v1/chat", json={}).status_code == 422
    assert test_client.post("/api/v1/chat", json={"query": "   "}).status_code == 422
    assert test_client.post("/api/v1/chat", json={"input": "legacy"}).status_code == 422
    assert (
        test_client.post(
            "/api/v1/chat", json={"query": "question", "image": "/etc/passwd"}
        ).status_code
        == 422
    )


def test_chat_stream_uses_one_json_sse_format(client) -> None:
    test_client, history = client
    response = test_client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": "stream", "query": "What is STR?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [event["type"] for event in events] == ["start", "chunk", "chunk", "end"]
    assert "".join(event.get("content", "") for event in events) == "Test answer"
    assert all(event["conversation_id"] == "stream" for event in events)
    assert all(event.get("source") == "generated" for event in events)
    from src.domain.models import DomainLabel, RiskLevel

    history.save_turn.assert_awaited_once_with(
        "stream",
        "What is STR?",
        "Test answer",
        DomainLabel.IN_DOMAIN,
        RiskLevel.STANDARD,
        owner_id="local-development",
    )


def test_clear_conversation(client) -> None:
    test_client, history = client
    response = test_client.delete("/api/v1/conversations/test")
    assert response.json() == {"status": "success", "deleted_turns": 1}
    history.clear_history.assert_awaited_once_with("test", owner_id="local-development")


def test_removed_legacy_endpoints_are_not_exposed(client) -> None:
    test_client, _ = client
    assert test_client.get("/api/v1/experts/current").status_code == 404
    assert test_client.post("/api/v1/clear/test").status_code == 404
    assert test_client.post("/api/v1/rag/clear-history/test").status_code == 404
    assert (
        test_client.post("/api/v1/rag/query", json={"query": "STR"}).status_code == 404
    )
