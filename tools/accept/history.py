"""Conversation and persistence acceptance."""

from __future__ import annotations

from uuid import uuid4

from .client import (
    chat_result,
    require_stream,
    stream_events,
)

from .proc import compose


DB_CONCURRENCY_CODE = r'''
import asyncio
from uuid import uuid4

import psycopg

from chatbot_app.database import (
    postgres_connection_string,
)
from chatbot_app.history import (
    get_conversation_repository,
)


OWNER_ID = "concurrency-acceptance"


async def cleanup(
    conversation_id,
):
    connection = (
        await psycopg.AsyncConnection.connect(
            postgres_connection_string()
        )
    )

    try:
        async with connection.transaction():
            await connection.execute(
                """
                DELETE FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
    finally:
        await connection.close()


async def main():
    repository = (
        get_conversation_repository()
    )

    conversation_id = uuid4()

    try:
        results = await asyncio.gather(
            repository.append_turn(
                conversation_id,
                owner_id=OWNER_ID,
                query="Concurrent query A",
                answer="Concurrent answer A",
                domain="in_domain",
                risk="standard",
                source="concurrency_acceptance",
            ),
            repository.append_turn(
                conversation_id,
                owner_id=OWNER_ID,
                query="Concurrent query B",
                answer="Concurrent answer B",
                domain="in_domain",
                risk="standard",
                source="concurrency_acceptance",
            ),
        )

        allocated = sorted(
            item.turn
            for item in results
        )

        if allocated != [1, 2]:
            raise RuntimeError(
                f"allocation failed: {allocated}"
            )

        persisted = (
            await repository.get_turns(
                conversation_id,
                owner_id=OWNER_ID,
                limit=10,
            )
        )

        turns = [
            item.turn
            for item in persisted
        ]

        if turns != [1, 2]:
            raise RuntimeError(
                f"unexpected turns: {turns}"
            )

        print(
            "DB CONCURRENCY ACCEPTANCE PASS"
        )

    finally:
        await cleanup(
            conversation_id
        )


asyncio.run(
    main()
)
'''


def history_suite() -> None:
    conversation_id = str(
        uuid4()
    )

    first = chat_result(
        (
            "FST cao hay thấp phản ánh "
            "mối quan hệ di truyền như thế nào "
            "giữa các quần thể?"
        ),
        conversation_id=(
            conversation_id
        ),
    )

    if first.get(
        "turn"
    ) != 1:
        raise RuntimeError(
            "expected first history turn=1"
        )

    second = chat_result(
        (
            "Biểu đồ Venn thể hiện mối quan hệ gì "
            "giữa các vùng dữ liệu trong hệ thống "
            "giám định?"
        ),
        conversation_id=(
            conversation_id
        ),
    )

    if second.get(
        "turn"
    ) != 2:
        raise RuntimeError(
            "expected second history turn=2"
        )

    print(
        "HISTORY ACCEPTANCE PASS"
    )


def context_suite() -> None:
    conversation_id = str(
        uuid4()
    )

    first = chat_result(
        (
            "FST cao hay thấp phản ánh "
            "mối quan hệ di truyền như thế nào "
            "giữa các quần thể?"
        ),
        conversation_id=(
            conversation_id
        ),
    )

    if first.get(
        "turn"
    ) != 1:
        raise RuntimeError(
            "context baseline turn is not 1"
        )

    second = chat_result(
        "Giải thích rõ hơn ý vừa rồi.",
        conversation_id=(
            conversation_id
        ),
    )

    if second.get(
        "turn"
    ) != 2:
        raise RuntimeError(
            "context follow-up turn is not 2"
        )

    decision = second.get(
        "decision"
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise RuntimeError(
            "context decision missing"
        )

    if decision.get(
        "domain"
    ) != "in_domain":
        raise RuntimeError(
            "safe follow-up was not "
            "resolved from context"
        )

    if decision.get(
        "risk"
    ) != "standard":
        raise RuntimeError(
            "safe contextual follow-up "
            "became high-risk"
        )

    reason = str(
        decision.get(
            "reason"
        )
        or ""
    )

    if not reason.startswith(
        "contextual_"
    ):
        raise RuntimeError(
            "expected contextual decision"
        )

    loaded = second.get(
        "history_turns_loaded"
    )

    if (
        not isinstance(
            loaded,
            int,
        )
        or loaded < 1
    ):
        raise RuntimeError(
            "history context was not loaded"
        )

    print(
        "PASS contextual follow-up"
    )

    conversation_id = str(
        uuid4()
    )

    first = chat_result(
        (
            "Quan hệ huyết thống trong "
            "giám định ADN là gì?"
        ),
        conversation_id=(
            conversation_id
        ),
    )

    first_decision = first.get(
        "decision"
    )

    if not isinstance(
        first_decision,
        dict,
    ):
        raise RuntimeError(
            "baseline risk decision missing"
        )

    if first_decision.get(
        "risk"
    ) != "standard":
        raise RuntimeError(
            "baseline context unexpectedly "
            "high-risk"
        )

    second = chat_result(
        "Hãy kết luận đi.",
        conversation_id=(
            conversation_id
        ),
    )

    decision = second.get(
        "decision"
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise RuntimeError(
            "high-risk decision missing"
        )

    if decision.get(
        "risk"
    ) != "high":
        raise RuntimeError(
            "context failed to preserve "
            "high-risk intent"
        )

    if second.get(
        "source"
    ) != "evidence_limitation":
        raise RuntimeError(
            "high-risk contextual request "
            "bypassed evidence policy"
        )

    print(
        "PASS contextual high-risk guard"
    )

    print(
        "CONTEXT ACCEPTANCE PASS"
    )


def history_concurrency_suite() -> None:
    compose(
        "exec",
        "-T",
        "chatbot",
        "python",
        "-",
        input_text=(
            DB_CONCURRENCY_CODE
        ),
    )


def stream_history_suite() -> None:
    conversation_id = str(
        uuid4()
    )

    first_events = stream_events(
        (
            "FST cao hay thấp phản ánh "
            "mối quan hệ di truyền như thế nào "
            "giữa các quần thể?"
        ),
        conversation_id=(
            conversation_id
        ),
    )

    _, first_end = require_stream(
        first_events
    )

    if first_end.get(
        "turn"
    ) != 1:
        raise RuntimeError(
            "streamed first turn is not 1"
        )

    second_events = stream_events(
        "Giải thích rõ hơn ý vừa rồi.",
        conversation_id=(
            conversation_id
        ),
    )

    _, second_end = require_stream(
        second_events
    )

    if second_end.get(
        "turn"
    ) != 2:
        raise RuntimeError(
            "streamed second turn is not 2"
        )

    loaded = second_end.get(
        "history_turns_loaded"
    )

    if (
        not isinstance(
            loaded,
            int,
        )
        or loaded < 1
    ):
        raise RuntimeError(
            "streamed follow-up did not "
            "load previous context"
        )

    decision = second_end.get(
        "decision"
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise RuntimeError(
            "stream decision missing"
        )

    if decision.get(
        "domain"
    ) != "in_domain":
        raise RuntimeError(
            "stream context follow-up "
            "was unresolved"
        )

    print(
        "STREAM HISTORY ACCEPTANCE PASS"
    )
