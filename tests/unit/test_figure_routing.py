"""Tests for configured figure request routing."""

import unittest

from chatbot_app.figure_routing import (
    is_direct_figure_request,
)


class FigureRoutingTests(
    unittest.TestCase
):
    def test_direct_description(
        self,
    ) -> None:
        self.assertTrue(
            is_direct_figure_request(
                "Giải thích hình này"
            )
        )

    def test_direct_analysis(
        self,
    ) -> None:
        self.assertTrue(
            is_direct_figure_request(
                "Phân tích heatmap này"
            )
        )

    def test_specific_comparison(
        self,
    ) -> None:
        self.assertFalse(
            is_direct_figure_request(
                "So sánh heatmap này với nhóm Asian"
            )
        )

    def test_specific_reason(
        self,
    ) -> None:
        self.assertFalse(
            is_direct_figure_request(
                "Tại sao heatmap có pattern này?"
            )
        )


if __name__ == "__main__":
    unittest.main()
