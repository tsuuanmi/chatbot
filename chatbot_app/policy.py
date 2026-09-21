"""Auditable domain and risk decisions built on semantic scores."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from chatbot_app.domain import ClassificationScores
from chatbot_app.text import normalize_for_policy


@dataclass(frozen=True, slots=True)
class DomainDecision:
    domain: str
    risk: str
    reason: str
    confidence: float
    margin: float
    risk_score: float
    matched_rule: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DomainPolicy:
    """Convert raw semantic scores into deterministic application decisions."""

    def __init__(self) -> None:
        path = Path(
            os.environ.get(
                "DOMAIN_POLICY_FILE",
                "/app/data/policies/domain_policy.json",
            )
        )

        if not path.is_file():
            raise RuntimeError(f"Domain policy file not found: {path}")

        with path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)

        domain = config["domain"]
        risk = config["risk"]

        self.minimum_confidence = float(
            domain["minimum_confidence"]
        )
        self.minimum_margin = float(
            domain["minimum_margin"]
        )

        self.semantic_risk_threshold = float(
            risk["semantic_fallback_threshold"]
        )

        self.decision_actions = tuple(
            normalize_for_policy(value)
            for value in risk["decision_actions"]
        )

        self.sensitive_subjects = tuple(
            normalize_for_policy(value)
            for value in risk["sensitive_subjects"]
        )

        self.direct_high_risk_phrases = tuple(
            normalize_for_policy(value)
            for value in risk["direct_high_risk_phrases"]
        )

    @staticmethod
    def _first_match(
        text: str,
        phrases: tuple[str, ...],
    ) -> str | None:
        for phrase in phrases:
            if phrase in text:
                return phrase

        return None

    def _explicit_high_risk(
        self,
        query: str,
    ) -> str | None:
        normalized = normalize_for_policy(query)

        direct = self._first_match(
            normalized,
            self.direct_high_risk_phrases,
        )

        if direct:
            return f"direct:{direct}"

        action = self._first_match(
            normalized,
            self.decision_actions,
        )

        subject = self._first_match(
            normalized,
            self.sensitive_subjects,
        )

        if action and subject:
            return f"action_subject:{action}+{subject}"

        return None

    def decide(
        self,
        query: str,
        scores: ClassificationScores,
    ) -> DomainDecision:
        explicit_rule = self._explicit_high_risk(query)

        if explicit_rule:
            return DomainDecision(
                domain="in_domain",
                risk="high",
                reason="explicit_high_risk_rule",
                confidence=scores.confidence,
                margin=scores.margin,
                risk_score=scores.risk_score,
                matched_rule=explicit_rule,
            )

        if scores.risk_score >= self.semantic_risk_threshold:
            return DomainDecision(
                domain="in_domain",
                risk="high",
                reason="semantic_high_risk",
                confidence=scores.confidence,
                margin=scores.margin,
                risk_score=scores.risk_score,
            )

        if (
            scores.confidence < self.minimum_confidence
            or scores.margin < self.minimum_margin
        ):
            return DomainDecision(
                domain="clarify",
                risk="standard",
                reason="low_semantic_confidence",
                confidence=scores.confidence,
                margin=scores.margin,
                risk_score=scores.risk_score,
            )

        return DomainDecision(
            domain=scores.best_label,
            risk="standard",
            reason="semantic_domain",
            confidence=scores.confidence,
            margin=scores.margin,
            risk_score=scores.risk_score,
        )


@lru_cache
def get_domain_policy() -> DomainPolicy:
    return DomainPolicy()
