"""Strict semantic classifier contract tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from loguru import logger

from src.common.exceptions import DomainClassifierError
from src.domain.classifier import DomainClassifier
from src.domain.models import DomainLabel, DomainReason


class FakeEmbedding:
    def __init__(self, query_vectors: dict[str, list[float]]) -> None:
        self.query_vectors = query_vectors

    def embed(self, text: str) -> list[float]:
        return self.query_vectors[text]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if len(texts) == 49:  # 24 in-domain, 15 out-of-domain, 10 clarify
            return (
                [[1.0, 0.0, 0.0]] * 24 + [[0.0, 1.0, 0.0]] * 15 + [[0.0, 0.0, 1.0]] * 10
            )
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.mark.asyncio
async def test_warmup_caches_reviewed_vectors() -> None:
    embedding = FakeEmbedding({})
    service = DomainClassifier(
        embedding,
        minimum_confidence=0.7,
        minimum_margin=0.03,
        high_risk_threshold=0.99,
    )

    assert not service.is_ready
    await service.warmup()
    assert service.is_ready


@pytest.mark.asyncio
async def test_warmup_fails_closed_when_embedding_is_unavailable() -> None:
    embedding = MagicMock()
    embedding.embed_batch.side_effect = RuntimeError("connection refused")
    service = DomainClassifier(
        embedding,
        minimum_confidence=0.7,
        minimum_margin=0.03,
        high_risk_threshold=0.99,
    )

    with pytest.raises(DomainClassifierError) as raised:
        await service.warmup()
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert not service.is_ready


@pytest.mark.asyncio
async def test_warmup_failure_logs_the_embedding_cause() -> None:
    embedding = MagicMock()
    embedding.embed_batch.side_effect = RuntimeError("connection refused")
    service = DomainClassifier(
        embedding,
        minimum_confidence=0.7,
        minimum_margin=0.03,
        high_risk_threshold=0.99,
    )
    messages: list[str] = []
    handler_id = logger.add(messages.append, level="ERROR")

    try:
        with pytest.raises(DomainClassifierError):
            await service.warmup()
    finally:
        logger.remove(handler_id)

    assert any(
        "connection refused" in message and "embedding" in message
        for message in messages
    )


@pytest.mark.asyncio
async def test_high_risk_similarity_overrides_ambiguity() -> None:
    service = classifier({"Kết luận mẫu của nghi phạm": [1.0, 0.0, 0.0]})
    service._high_risk_threshold = 0.99
    decision = await service.classify("Kết luận mẫu của nghi phạm")
    assert decision.label is DomainLabel.IN_DOMAIN
    assert decision.risk.value == "HIGH_RISK"


def test_domain_evaluation_data_uses_constrained_labels() -> None:
    path = Path(__file__).parent / "data" / "domain_evaluation.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) >= 15
    assert {record["label"] for record in records} == {
        label.value for label in DomainLabel
    }


def classifier(query_vectors: dict[str, list[float]]) -> DomainClassifier:
    return DomainClassifier(
        FakeEmbedding(query_vectors),
        minimum_confidence=0.7,
        minimum_margin=0.03,
        high_risk_threshold=0.99,
    )


@pytest.mark.asyncio
async def test_semantic_classifier_rejects_unrelated_intent() -> None:
    decision = await classifier({"Nấu món ăn": [0.0, 1.0, 0.0]}).classify("Nấu món ăn")
    assert decision.label is DomainLabel.OUT_OF_DOMAIN
    assert decision.reason is DomainReason.UNRELATED_TOPIC


@pytest.mark.asyncio
async def test_semantic_classifier_accepts_forensic_genetics() -> None:
    decision = await classifier({"Giải thích STR": [1.0, 0.0, 0.0]}).classify(
        "Giải thích STR"
    )
    assert decision.label is DomainLabel.IN_DOMAIN


@pytest.mark.asyncio
async def test_ambiguous_follow_up_inherits_only_persisted_in_domain_decision() -> None:
    service = classifier({"Cấu trúc của nó": [0.0, 0.0, 1.0]})
    without_context = await service.classify("Cấu trúc của nó")
    with_context = await service.classify("Cấu trúc của nó", prior_in_domain=True)
    assert without_context.label is DomainLabel.CLARIFY
    assert with_context.label is DomainLabel.IN_DOMAIN
    assert with_context.reason is DomainReason.CONTEXTUAL_FOLLOW_UP


@pytest.mark.asyncio
async def test_unrelated_image_requires_clarification() -> None:
    decision = await classifier({"Giải thích ảnh món ăn": [0.0, 1.0, 0.0]}).classify(
        "Giải thích ảnh món ăn", has_image=True
    )
    assert decision.label is DomainLabel.CLARIFY


@pytest.mark.asyncio
async def test_configured_figure_is_explicitly_supported_without_embedding() -> None:
    embedding = MagicMock()
    service = DomainClassifier(
        embedding,
        minimum_confidence=0.7,
        minimum_margin=0.03,
        high_risk_threshold=0.8,
    )
    decision = await service.classify("Hình bar3", configured_figure=True)
    assert decision.label is DomainLabel.IN_DOMAIN
    assert decision.reason is DomainReason.CONFIGURED_FIGURE
    embedding.embed.assert_not_called()
