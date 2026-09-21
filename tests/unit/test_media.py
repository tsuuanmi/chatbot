"""Tests for safe figure and image request primitives."""

from __future__ import annotations

import base64
import unittest

from chatbot_app.media import (
    normalize_figure_id,
    parse_image_input,
    validate_media_input,
)


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"test-payload"
)

JPEG_BYTES = (
    b"\xff\xd8\xff"
    b"\xdbtest-payload"
)

WEBP_BYTES = (
    b"RIFF"
    b"\x04\x00\x00\x00"
    b"WEBP"
    b"test"
)


def encoded(
    value: bytes,
) -> str:
    return base64.b64encode(
        value
    ).decode("ascii")


class FigureIdTests(
    unittest.TestCase
):
    def test_normalizes_figure_id(
        self,
    ) -> None:
        self.assertEqual(
            normalize_figure_id(
                "  HEATMAP1  "
            ),
            "heatmap1",
        )

    def test_allows_safe_identifier(
        self,
    ) -> None:
        self.assertEqual(
            normalize_figure_id(
                "fst_heatmap-2"
            ),
            "fst_heatmap-2",
        )

    def test_rejects_path_traversal(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            normalize_figure_id(
                "../heatmap1"
            )

    def test_rejects_extension(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            normalize_figure_id(
                "heatmap1.png"
            )

    def test_rejects_empty_identifier(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            normalize_figure_id(
                "   "
            )


class ImageInputTests(
    unittest.TestCase
):
    def test_raw_png_base64(
        self,
    ) -> None:
        image = parse_image_input(
            encoded(PNG_BYTES)
        )

        self.assertIsNotNone(image)
        assert image is not None

        self.assertEqual(
            image.mime_type,
            "image/png",
        )

        self.assertEqual(
            image.byte_size,
            len(PNG_BYTES),
        )

    def test_png_data_url(
        self,
    ) -> None:
        payload = encoded(
            PNG_BYTES
        )

        image = parse_image_input(
            (
                "data:image/png;base64,"
                + payload
            )
        )

        self.assertIsNotNone(image)
        assert image is not None

        self.assertEqual(
            image.mime_type,
            "image/png",
        )

        self.assertEqual(
            image.data_url,
            (
                "data:image/png;base64,"
                + payload
            ),
        )

    def test_jpeg_data_url(
        self,
    ) -> None:
        image = parse_image_input(
            (
                "data:image/jpeg;base64,"
                + encoded(JPEG_BYTES)
            )
        )

        self.assertIsNotNone(image)
        assert image is not None

        self.assertEqual(
            image.mime_type,
            "image/jpeg",
        )

    def test_webp_raw_base64(
        self,
    ) -> None:
        image = parse_image_input(
            encoded(WEBP_BYTES)
        )

        self.assertIsNotNone(image)
        assert image is not None

        self.assertEqual(
            image.mime_type,
            "image/webp",
        )

    def test_rejects_invalid_base64(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            parse_image_input(
                "not-valid-base64!!"
            )

    def test_rejects_unknown_format(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            parse_image_input(
                encoded(
                    b"not-an-image"
                )
            )

    def test_rejects_mime_mismatch(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            parse_image_input(
                (
                    "data:image/png;base64,"
                    + encoded(JPEG_BYTES)
                )
            )

    def test_rejects_unsupported_mime(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            parse_image_input(
                (
                    "data:image/gif;base64,"
                    + encoded(
                        b"GIF89a"
                    )
                )
            )

    def test_rejects_oversized_image(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            parse_image_input(
                encoded(PNG_BYTES),
                max_bytes=4,
            )


class MediaInputTests(
    unittest.TestCase
):
    def test_text_only(
        self,
    ) -> None:
        figure_id, image = (
            validate_media_input()
        )

        self.assertIsNone(
            figure_id
        )
        self.assertIsNone(
            image
        )

    def test_figure_only(
        self,
    ) -> None:
        figure_id, image = (
            validate_media_input(
                figure_id="HEATMAP1",
            )
        )

        self.assertEqual(
            figure_id,
            "heatmap1",
        )
        self.assertIsNone(
            image
        )

    def test_image_only(
        self,
    ) -> None:
        figure_id, image = (
            validate_media_input(
                image=encoded(
                    PNG_BYTES
                ),
            )
        )

        self.assertIsNone(
            figure_id
        )
        self.assertIsNotNone(
            image
        )

    def test_rejects_figure_and_image(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            validate_media_input(
                figure_id="heatmap1",
                image=encoded(
                    PNG_BYTES
                ),
            )


if __name__ == "__main__":
    unittest.main()
