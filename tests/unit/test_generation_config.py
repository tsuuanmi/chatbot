"""Regression tests for generation configuration."""

from __future__ import annotations

import unittest
from pathlib import Path


class GenerationConfigurationTests(
    unittest.TestCase
):
    def test_output_limit_is_not_hard_coded(
        self,
    ) -> None:
        source = Path(
            "chatbot_app/forensic_chat.py"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '"LLAMA_MAX_OUTPUT_TOKENS"',
            source,
        )

        self.assertIn(
            "default=2048",
            source,
        )

        self.assertIn(
            '"max_tokens": self.generation_max_output_tokens,',
            source,
        )

        self.assertNotIn(
            '"max_tokens": 512,',
            source,
        )

    def test_runtime_surfaces_output_limit(
        self,
    ) -> None:
        env = Path(
            ".env.example"
        ).read_text(
            encoding="utf-8"
        )

        compose = Path(
            "compose.yaml"
        ).read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "LLAMA_MAX_OUTPUT_TOKENS=2048",
            env,
        )

        self.assertIn(
            (
                "LLAMA_MAX_OUTPUT_TOKENS: "
                "${LLAMA_MAX_OUTPUT_TOKENS:-2048}"
            ),
            compose,
        )


if __name__ == "__main__":
    unittest.main()
