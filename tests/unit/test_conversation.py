"""Unit tests for bounded conversation context."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from uuid import uuid4

from chatbot_app.conversation import (
    ConversationLockRegistry,
    HistoryContextBuilder,
    bounded_env_int,
)


@dataclass
class Turn:
    query: str
    answer: str
    domain: str
    risk: str


class HistoryContextBuilderTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.builder = HistoryContextBuilder(
            max_turns=6,
            max_chars=8000,
        )

    def test_historical_citations_are_removed(
        self,
    ) -> None:
        turns = [
            Turn(
                query="FST là gì?",
                answer=(
                    "Nội dung [cite:old:1] "
                    "giữ [1] và [DNA]."
                ),
                domain="in_domain",
                risk="standard",
            )
        ]

        messages = (
            self.builder.prompt_messages(
                turns
            )
        )

        assistant_messages = [
            item.content
            for item in messages
            if item.role == "assistant"
        ]

        self.assertEqual(
            len(assistant_messages),
            1,
        )

        answer = assistant_messages[0]

        self.assertNotIn(
            "[cite:old:1]",
            answer,
        )
        self.assertIn(
            "[1]",
            answer,
        )
        self.assertIn(
            "[DNA]",
            answer,
        )

    def test_standard_in_domain_turn_can_resolve_context(
        self,
    ) -> None:
        turns = [
            Turn(
                query="FST là gì?",
                answer="Giải thích FST.",
                domain="in_domain",
                risk="standard",
            )
        ]

        contextual = (
            self.builder.contextual_query(
                "Giải thích rõ hơn.",
                turns,
            )
        )

        self.assertIsNotNone(
            contextual
        )
        self.assertIn(
            "FST là gì?",
            contextual or "",
        )
        self.assertIn(
            "Giải thích rõ hơn.",
            contextual or "",
        )

    def test_high_risk_turn_is_not_used_to_resolve_context(
        self,
    ) -> None:
        turns = [
            Turn(
                query=(
                    "Xác nhận người A "
                    "là cha ruột."
                ),
                answer=(
                    "Không thể kết luận."
                ),
                domain="in_domain",
                risk="high",
            )
        ]

        contextual = (
            self.builder.contextual_query(
                "Giải thích thêm.",
                turns,
            )
        )

        self.assertIsNone(
            contextual
        )

    def test_out_of_domain_turn_is_not_used_to_resolve_context(
        self,
    ) -> None:
        turns = [
            Turn(
                query="So sánh iPhone.",
                answer="Ngoài phạm vi.",
                domain="out_of_domain",
                risk="standard",
            )
        ]

        self.assertIsNone(
            self.builder.contextual_query(
                "Nói rõ hơn.",
                turns,
            )
        )

    def test_history_is_bounded_by_turn_count(
        self,
    ) -> None:
        builder = HistoryContextBuilder(
            max_turns=2,
            max_chars=8000,
        )

        turns = [
            Turn(
                query=f"Q{index}",
                answer=f"A{index}",
                domain="in_domain",
                risk="standard",
            )
            for index in range(5)
        ]

        messages = (
            builder.prompt_messages(
                turns
            )
        )

        contents = [
            message.content
            for message in messages
        ]

        self.assertEqual(
            contents,
            [
                "Q3",
                "A3",
                "Q4",
                "A4",
            ],
        )

    def test_history_is_bounded_by_character_budget(
        self,
    ) -> None:
        builder = HistoryContextBuilder(
            max_turns=6,
            max_chars=20,
        )

        turns = [
            Turn(
                query="Q" * 30,
                answer="A" * 30,
                domain="in_domain",
                risk="standard",
            )
        ]

        messages = (
            builder.prompt_messages(
                turns
            )
        )

        total = sum(
            len(item.content)
            for item in messages
        )

        self.assertLessEqual(
            total,
            20,
        )


class ConversationLockRegistryTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_idle_lock_is_removed(
        self,
    ) -> None:
        registry = (
            ConversationLockRegistry()
        )

        conversation_id = uuid4()

        self.assertEqual(
            registry.active_entries,
            0,
        )

        async with registry.hold(
            conversation_id
        ):
            self.assertEqual(
                registry.active_entries,
                1,
            )

        self.assertEqual(
            registry.active_entries,
            0,
        )

    async def test_same_conversation_is_serialized(
        self,
    ) -> None:
        registry = (
            ConversationLockRegistry()
        )

        conversation_id = uuid4()

        order: list[str] = []

        first_entered = (
            __import__("asyncio").Event()
        )

        async def first() -> None:
            async with registry.hold(
                conversation_id
            ):
                order.append(
                    "first-enter"
                )

                first_entered.set()

                await __import__(
                    "asyncio"
                ).sleep(0.05)

                order.append(
                    "first-exit"
                )

        async def second() -> None:
            await first_entered.wait()

            async with registry.hold(
                conversation_id
            ):
                order.append(
                    "second-enter"
                )

        await __import__(
            "asyncio"
        ).gather(
            first(),
            second(),
        )

        self.assertEqual(
            order,
            [
                "first-enter",
                "first-exit",
                "second-enter",
            ],
        )

        self.assertEqual(
            registry.active_entries,
            0,
        )


if __name__ == "__main__":
    unittest.main()
