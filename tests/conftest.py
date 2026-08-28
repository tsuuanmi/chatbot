"""Shared isolated API fixtures."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.domain.models import DomainDecision, DomainLabel, DomainReason, RiskLevel


@pytest.fixture
def workflow_result() -> dict:
    return {
        "final_answer": "Test answer",
        "response_source": "generated",
        "conversation_status": "active",
        "figure_description": None,
        "used_citation_ids": [],
        "domain_decision": DomainDecision(
            label=DomainLabel.IN_DOMAIN,
            risk=RiskLevel.STANDARD,
            reason=DomainReason.FORENSIC_GENETICS,
            confidence=1.0,
        ),
    }


@pytest.fixture
def client(workflow_result: dict):
    history = AsyncMock()
    history.connect.return_value = None
    history.close.return_value = None
    history.get_latest_domain_label.return_value = None
    history.claim_conversation.return_value = True
    history.get_conversation_owner.return_value = None
    history.save_turn.return_value = 1
    history.clear_history.return_value = 1

    async def stream(*args, **kwargs):
        state = {
            "response_source": "generated",
            "conversation_status": "active",
            "figure_description": None,
            "used_citation_ids": [],
            "domain_decision": DomainDecision(
                label=DomainLabel.IN_DOMAIN,
                risk=RiskLevel.STANDARD,
                reason=DomainReason.FORENSIC_GENETICS,
                confidence=1.0,
            ),
        }

        async def tokens() -> AsyncGenerator[str, None]:
            yield "Test "
            yield "answer"

        return state, tokens()

    with (
        patch(
            "src.api.auth.get_settings",
            return_value=SimpleNamespace(api_auth_enabled=False),
        ),
        patch("src.api.app.setup_container"),
        patch("src.api.app.close_container"),
        patch("src.api.app.warmup_application", new=AsyncMock()),
        patch("src.api.app.get_history_service", return_value=history),
        patch("src.api.v1.chat.get_history_service", return_value=history),
        patch(
            "src.api.v1.chat.run_workflow", new=AsyncMock(return_value=workflow_result)
        ),
        patch("src.api.v1.chat.stream_workflow", side_effect=stream),
        TestClient(create_app()) as test_client,
    ):
        yield test_client, history
