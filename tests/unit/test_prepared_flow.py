"""Regression tests for approved prepared-answer routing."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chatbot_app.prepared import PreparedAnswerRepository


class PreparedRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()

        self.path = (
            Path(self.temporary.name)
            / "knowledge_base.tsv"
        )

        columns = [
            "no",
            "term",
            "description",
            "keywords",
            "aliases",
            "topic",
            "figure_id",
            "source_id",
            "source_title",
            "source_authority",
            "source_version",
            "source_page_or_section",
            "effective_date",
            "reviewed_at",
            "reviewer",
            "approval_status",
        ]

        rows = [
            [
                "1",
                "STR là gì?",
                (
                    "STR là viết tắt của "
                    "Short Tandem Repeats."
                ),
                "STR|Short Tandem Repeats",
                (
                    "Short Tandem Repeats là gì?"
                    "|STR nghĩa là gì?"
                ),
                "forensic_faq",
                "",
                "internal-faq",
                "Forensic FAQ",
                "Reviewed project content",
                "1.0",
                "str",
                "2026-09-06",
                "2026-09-06",
                "test",
                "approved",
            ],
            [
                "2",
                "Câu hỏi chưa phê duyệt",
                "Không được phép trả trực tiếp.",
                "",
                "",
                "forensic_faq",
                "",
                "internal-faq",
                "Forensic FAQ",
                "Reviewed project content",
                "1.0",
                "draft",
                "2026-09-06",
                "",
                "",
                "draft",
            ],
        ]

        content = [
            "\t".join(columns),
            *(
                "\t".join(row)
                for row in rows
            ),
        ]

        self.path.write_text(
            "\n".join(content) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def repository(
        self,
    ) -> PreparedAnswerRepository:
        with patch.dict(
            os.environ,
            {
                "KNOWLEDGE_BASE_FILE": str(
                    self.path
                ),
            },
        ):
            return PreparedAnswerRepository()

    def test_normalized_exact_question_matches(
        self,
    ) -> None:
        answer = self.repository().find(
            "   str LÀ GÌ!!!   "
        )

        self.assertIsNotNone(answer)
        assert answer is not None

        self.assertEqual(
            answer.number,
            "1",
        )

        self.assertEqual(
            answer.answer,
            (
                "STR là viết tắt của "
                "Short Tandem Repeats."
            ),
        )

    def test_alias_matches(
        self,
    ) -> None:
        answer = self.repository().find(
            "STR nghĩa là gì?"
        )

        self.assertIsNotNone(answer)
        assert answer is not None

        self.assertEqual(
            answer.number,
            "1",
        )

    def test_alias_normalization_matches(
        self,
    ) -> None:
        answer = self.repository().find(
            " short tandem repeats LÀ GÌ!!! "
        )

        self.assertIsNotNone(answer)
        assert answer is not None

        self.assertEqual(
            answer.number,
            "1",
        )

    def test_similar_but_not_exact_does_not_match(
        self,
    ) -> None:
        answer = self.repository().find(
            (
                "Hãy giải thích chi tiết STR "
                "trong giám định ADN"
            )
        )

        self.assertIsNone(answer)

    def test_unapproved_record_does_not_match(
        self,
    ) -> None:
        answer = self.repository().find(
            "Câu hỏi chưa phê duyệt"
        )

        self.assertIsNone(answer)


class PreparedRoutingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            Path(__file__).resolve()
            .parents[2]
            / "chatbot_app"
            / "forensic_chat.py"
        )

        cls.source = cls.path.read_text(
            encoding="utf-8"
        )

        tree = ast.parse(
            cls.source,
            filename=str(cls.path),
        )

        cls.answer_core = cls._function_source(
            tree,
            "_answer_core",
        )

        cls.prepared_response = cls._function_source(
            tree,
            "_prepared_response",
        )

    @classmethod
    def _function_source(
        cls,
        tree: ast.AST,
        name: str,
    ) -> str:
        for node in ast.walk(tree):
            if (
                isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                and node.name == name
            ):
                value = ast.get_source_segment(
                    cls.source,
                    node,
                )

                if value is None:
                    raise AssertionError(
                        f"Unable to read {name}"
                    )

                return value

        raise AssertionError(
            f"Function not found: {name}"
        )

    def test_classification_runs_before_prepared_lookup(
        self,
    ) -> None:
        classification = (
            self.answer_core.index(
                "self.classifier.classify"
            )
        )

        prepared = self.answer_core.index(
            "self.prepared.find"
        )

        self.assertLess(
            classification,
            prepared,
        )

    def test_high_risk_gate_runs_before_prepared_return(
        self,
    ) -> None:
        high_risk = self.answer_core.index(
            'if decision.risk == "high":'
        )

        prepared_return = self.answer_core.index(
            (
                "if prepared is not None "
                "and image is None:"
            )
        )

        self.assertLess(
            high_risk,
            prepared_return,
        )

    def test_prepared_return_runs_before_standard_retrieval(
        self,
    ) -> None:
        prepared_return = self.answer_core.index(
            (
                "if prepared is not None "
                "and image is None:"
            )
        )

        retrieval = self.answer_core.index(
            "self.retriever.retrieve"
        )

        self.assertLess(
            prepared_return,
            retrieval,
        )

    def test_raw_image_disables_prepared_shortcut(
        self,
    ) -> None:
        self.assertIn(
            (
                "if prepared is not None "
                "and image is None:"
            ),
            self.answer_core,
        )

    def test_prepared_response_is_direct(
        self,
    ) -> None:
        self.assertIn(
            '"source": "prepared_answer"',
            self.prepared_response,
        )

        self.assertIn(
            "prepared.answer",
            self.prepared_response,
        )

        self.assertIn(
            "prepared.citation()",
            self.prepared_response,
        )

        self.assertNotIn(
            "self.retriever",
            self.prepared_response,
        )

        self.assertNotIn(
            "self._generate",
            self.prepared_response,
        )


if __name__ == "__main__":
    unittest.main()
