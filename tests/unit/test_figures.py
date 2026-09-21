"""Tests for configured figure inventory identity."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chatbot_app.figures import (
    scan_figures,
)


PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"payload"
)


class FigureInventoryTests(
    unittest.TestCase
):
    def test_scans_figure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            (
                root / "HEATMAP1.png"
            ).write_bytes(PNG)

            assets = scan_figures(
                root
            )

            self.assertEqual(
                len(assets),
                1,
            )

            self.assertEqual(
                assets[0].figure_id,
                "heatmap1",
            )

            self.assertEqual(
                assets[0].mime_type,
                "image/png",
            )

    def test_hash_depends_on_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = (
                root / "heatmap1.png"
            )

            path.write_bytes(PNG)

            first = scan_figures(
                root
            )[0]

            path.touch()

            second = scan_figures(
                root
            )[0]

            self.assertEqual(
                first.content_hash,
                second.content_hash,
            )

            path.write_bytes(
                PNG + b"changed"
            )

            third = scan_figures(
                root
            )[0]

            self.assertNotEqual(
                first.content_hash,
                third.content_hash,
            )

    def test_rejects_duplicate_ids(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            (
                root / "figure1.png"
            ).write_bytes(PNG)

            (
                root / "figure1.jpg"
            ).write_bytes(
                b"\xff\xd8\xffpayload"
            )

            with self.assertRaises(
                RuntimeError
            ):
                scan_figures(
                    root
                )

    def test_ignores_unrelated_files(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            (
                root / "notes.txt"
            ).write_text(
                "ignored",
                encoding="utf-8",
            )

            self.assertEqual(
                scan_figures(root),
                [],
            )


if __name__ == "__main__":
    unittest.main()
