"""Diagnostic domain/risk decision endpoint."""

from hayhooks import BasePipelineWrapper

from chatbot_app.domain import (
    get_domain_classifier,
)
from chatbot_app.policy import (
    get_domain_policy,
)


class PipelineWrapper(BasePipelineWrapper):
    skip_mcp = True

    def setup(self) -> None:
        self.classifier = get_domain_classifier()
        self.policy = get_domain_policy()

    def run_api(
        self,
        query: str,
    ) -> dict[str, object]:
        scores = self.classifier.classify(
            query
        )

        decision = self.policy.decide(
            query,
            scores,
        )

        return {
            "decision": decision.to_dict(),
            "raw": {
                "best_label": scores.best_label,
                "confidence": scores.confidence,
                "margin": scores.margin,
                "risk_score": scores.risk_score,
                "class_scores": scores.class_scores,
            },
        }
