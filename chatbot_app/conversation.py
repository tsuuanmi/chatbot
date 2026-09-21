"""Bounded conversational context and request coordination."""

from __future__ import annotations

import asyncio
import os
from collections.abc import (
    AsyncIterator,
    Sequence,
)
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from chatbot_app.citations import (
    sanitize_citations,
)


class ConversationTurnLike(Protocol):
    query: str
    answer: str
    domain: str
    risk: str


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    role: str
    content: str


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


def bounded_env_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.environ.get(
        name,
        str(default),
    ).strip()

    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(
            f"{name} must be an integer"
        ) from error

    if not minimum <= value <= maximum:
        raise RuntimeError(
            f"{name} must be between "
            f"{minimum} and {maximum}"
        )

    return value


class ConversationLockRegistry:
    """Serialize one conversation without retaining idle locks."""

    def __init__(self) -> None:
        self._entries: dict[
            str,
            _LockEntry,
        ] = {}

        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(
        self,
        conversation_id: UUID,
    ) -> AsyncIterator[None]:
        key = str(conversation_id)

        async with self._guard:
            entry = self._entries.get(key)

            if entry is None:
                entry = _LockEntry(
                    lock=asyncio.Lock()
                )
                self._entries[key] = entry

            entry.users += 1

        try:
            async with entry.lock:
                yield
        finally:
            async with self._guard:
                entry.users -= 1

                if entry.users == 0:
                    self._entries.pop(
                        key,
                        None,
                    )

    @property
    def active_entries(self) -> int:
        return len(self._entries)


class HistoryContextBuilder:
    """Build bounded non-evidentiary conversational context."""

    def __init__(
        self,
        *,
        max_turns: int,
        max_chars: int,
    ) -> None:
        self.max_turns = max_turns
        self.max_chars = max_chars

    def contextual_query(
        self,
        current_query: str,
        turns: Sequence[
            ConversationTurnLike
        ],
    ) -> str | None:
        """Resolve an ambiguous request from one safe prior user turn.

        Only a prior STANDARD + IN_DOMAIN user request may supply
        conversational context. Previous assistant answers are never
        used for policy classification.
        """

        for turn in reversed(turns):
            if (
                turn.domain == "in_domain"
                and turn.risk == "standard"
            ):
                previous = turn.query.strip()

                if previous:
                    return (
                        f"{previous}\n"
                        f"{current_query}"
                    )

        return None

    def prompt_messages(
        self,
        turns: Sequence[
            ConversationTurnLike
        ],
    ) -> list[HistoryMessage]:
        candidates = [
            turn
            for turn in turns
            if turn.domain == "in_domain"
        ][-self.max_turns :]

        selected: list[
            tuple[str, str]
        ] = []

        remaining = self.max_chars

        for turn in reversed(
            candidates
        ):
            user_text = (
                turn.query.strip()
            )

            assistant_text = (
                sanitize_citations(
                    turn.answer,
                    set(),
                ).strip()
            )

            size = (
                len(user_text)
                + len(assistant_text)
            )

            if size <= remaining:
                selected.append(
                    (
                        user_text,
                        assistant_text,
                    )
                )
                remaining -= size
                continue

            if not selected and remaining > 0:
                user_budget = min(
                    len(user_text),
                    remaining // 2,
                )

                clipped_user = self._clip(
                    user_text,
                    user_budget,
                )

                assistant_budget = max(
                    0,
                    remaining
                    - len(clipped_user),
                )

                clipped_assistant = self._clip(
                    assistant_text,
                    assistant_budget,
                )

                if (
                    clipped_user
                    or clipped_assistant
                ):
                    selected.append(
                        (
                            clipped_user,
                            clipped_assistant,
                        )
                    )

            break

        selected.reverse()

        messages: list[
            HistoryMessage
        ] = []

        for user_text, assistant_text in selected:
            if user_text:
                messages.append(
                    HistoryMessage(
                        role="user",
                        content=user_text,
                    )
                )

            if assistant_text:
                messages.append(
                    HistoryMessage(
                        role="assistant",
                        content=assistant_text,
                    )
                )

        return messages

    @staticmethod
    def _clip(
        text: str,
        limit: int,
    ) -> str:
        if limit <= 0:
            return ""

        if len(text) <= limit:
            return text

        if limit == 1:
            return "…"

        return (
            text[: limit - 1]
            + "…"
        )
