"""Semantic domain and risk scoring for forensic-genetics queries."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding


@dataclass(frozen=True, slots=True)
class ClassificationScores:
    best_label: str
    confidence: float
    margin: float
    class_scores: dict[str, float]
    risk_score: float


class DomainClassifier:
    """Score queries against reviewed semantic exemplars."""

    def __init__(self) -> None:
        policy_path = Path(
            os.environ.get(
                "DOMAIN_EXEMPLARS_FILE",
                "/app/data/policies/domain_exemplars.json",
            )
        )

        if not policy_path.is_file():
            raise RuntimeError(
                f"Domain exemplar file not found: {policy_path}"
            )

        with policy_path.open("r", encoding="utf-8") as handle:
            policy = json.load(handle)

        self._model = TextEmbedding(
            model_name=os.environ["EMBEDDING_MODEL"],
            cache_dir=os.environ["FASTEMBED_CACHE_PATH"],
            threads=int(os.environ.get("EMBEDDING_THREADS", "4")),
            providers=["CPUExecutionProvider"],
            local_files_only=True,
        )

        self._prototypes: dict[str, np.ndarray] = {}

        for label in ("in_domain", "out_of_domain", "clarify"):
            texts = policy[label]

            self._prototypes[label] = np.asarray(
                list(self._model.embed(texts)),
                dtype=np.float32,
            )

        self._risk_vectors = np.asarray(
            list(self._model.embed(policy["high_risk"])),
            dtype=np.float32,
        )

    @staticmethod
    def _cosine_many(
        query: np.ndarray,
        matrix: np.ndarray,
    ) -> np.ndarray:
        query_norm = np.linalg.norm(query)

        matrix_norms = np.linalg.norm(
            matrix,
            axis=1,
        )

        denominator = matrix_norms * query_norm

        scores = np.zeros(
            matrix.shape[0],
            dtype=np.float32,
        )

        valid = denominator > 0

        scores[valid] = (
            matrix[valid] @ query
        ) / denominator[valid]

        return scores

    def classify(
        self,
        query: str,
    ) -> ClassificationScores:
        query = query.strip()

        if not query:
            raise ValueError("query must not be empty")

        vector = np.asarray(
            next(iter(self._model.embed([query]))),
            dtype=np.float32,
        )

        class_scores = {
            label: float(
                self._cosine_many(
                    vector,
                    prototypes,
                ).max()
            )
            for label, prototypes in self._prototypes.items()
        }

        ranked = sorted(
            class_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        best_label, confidence = ranked[0]
        margin = confidence - ranked[1][1]

        risk_score = float(
            self._cosine_many(
                vector,
                self._risk_vectors,
            ).max()
        )

        return ClassificationScores(
            best_label=best_label,
            confidence=confidence,
            margin=margin,
            class_scores=class_scores,
            risk_score=risk_score,
        )


@lru_cache
def get_domain_classifier() -> DomainClassifier:
    return DomainClassifier()
