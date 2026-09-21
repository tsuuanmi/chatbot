"""Tests for bounded model-generation admission."""

from __future__ import annotations

import unittest

from chatbot_app.capacity import (
    GenerationAdmissionController,
    GenerationBusyError,
)


class GenerationAdmissionTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_second_request_times_out(
        self,
    ) -> None:
        controller = (
            GenerationAdmissionController(
                limit=1,
                queue_timeout_seconds=0.02,
            )
        )

        async with controller.slot():
            with self.assertRaises(
                GenerationBusyError
            ) as caught:
                async with controller.slot():
                    self.fail(
                        "second slot must not be acquired"
                    )

        self.assertEqual(
            caught.exception.retry_after_seconds,
            1,
        )

    async def test_slot_is_released_normally(
        self,
    ) -> None:
        controller = (
            GenerationAdmissionController(
                limit=1,
                queue_timeout_seconds=0.1,
            )
        )

        async with controller.slot():
            pass

        async with controller.slot():
            pass

    async def test_slot_is_released_after_exception(
        self,
    ) -> None:
        controller = (
            GenerationAdmissionController(
                limit=1,
                queue_timeout_seconds=0.1,
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            async with controller.slot():
                raise RuntimeError("test")

        async with controller.slot():
            pass


if __name__ == "__main__":
    unittest.main()
