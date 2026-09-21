"""Tests for absolute semantic RAG relevance."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from chatbot_app.relevance import (
    is_semantically_relevant,
    minimum_semantic_score,
)


class RelevanceConfigurationTests(unittest.TestCase):
    def test_default_threshold_is_calibrated_value(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            self.assertEqual(
                minimum_semantic_score(),
                0.68,
            )

    def test_threshold_can_be_overridden(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "RAG_MIN_SEMANTIC_SCORE": "0.72",
            },
            clear=True,
        ):
            self.assertEqual(
                minimum_semantic_score(),
                0.72,
            )

    def test_invalid_threshold_is_rejected(
        self,
    ) -> None:
        for value in (
            "invalid",
            "-0.01",
            "1.01",
            "nan",
            "inf",
        ):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {
                        "RAG_MIN_SEMANTIC_SCORE": value,
                    },
                    clear=True,
                ):
                    with self.assertRaises(
                        RuntimeError
                    ):
                        minimum_semantic_score()


class RelevanceDecisionTests(unittest.TestCase):
    def test_semantic_gate(
        self,
    ) -> None:
        self.assertTrue(
            is_semantically_relevant(
                0.68,
                0.68,
            )
        )

        self.assertTrue(
            is_semantically_relevant(
                0.81,
                0.68,
            )
        )

        self.assertFalse(
            is_semantically_relevant(
                0.6775,
                0.68,
            )
        )

        self.assertFalse(
            is_semantically_relevant(
                None,
                0.68,
            )
        )


class EvidencePolicyContractTests(unittest.TestCase):
    def test_evidence_policy_applies_gate_before_selection(
        self,
    ) -> None:
        source = Path(
            "chatbot_app/evidence.py"
        ).read_text(
            encoding="utf-8"
        )

        score_lookup = source.index(
            "semantic_score = semantic_scores.get("
        )

        gate = source.index(
            "if not is_semantically_relevant("
        )

        selection = source.index(
            "selected.append("
        )

        self.assertLess(
            score_lookup,
            gate,
        )

        self.assertLess(
            gate,
            selection,
        )


if __name__ == "__main__":
    unittest.main()
