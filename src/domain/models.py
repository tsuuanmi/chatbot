"""Typed semantic-domain decisions."""

from enum import StrEnum

from pydantic import BaseModel


class DomainLabel(StrEnum):
    IN_DOMAIN = "IN_DOMAIN"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    CLARIFY = "CLARIFY"


class RiskLevel(StrEnum):
    STANDARD = "STANDARD"
    HIGH_RISK = "HIGH_RISK"


class DomainReason(StrEnum):
    FORENSIC_GENETICS = "FORENSIC_GENETICS"
    CONFIGURED_FIGURE = "CONFIGURED_FIGURE"
    CONTEXTUAL_FOLLOW_UP = "CONTEXTUAL_FOLLOW_UP"
    UNRELATED_TOPIC = "UNRELATED_TOPIC"
    AMBIGUOUS_CONTEXT = "AMBIGUOUS_CONTEXT"
    CASE_SPECIFIC_CONCLUSION = "CASE_SPECIFIC_CONCLUSION"


class DomainDecision(BaseModel):
    label: DomainLabel
    risk: RiskLevel
    reason: DomainReason
    confidence: float
