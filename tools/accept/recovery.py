"""Persistent state restart/recovery acceptance."""

from __future__ import annotations

from uuid import uuid4

from .client import chat_result
from .proc import compose


def wait_service(
    service: str,
) -> None:
    compose(
        "up",
        "-d",
        "--pull",
        "never",
        "--no-deps",
        "--wait",
        service,
    )


def recovery_suite() -> None:
    conversation_id = str(
        uuid4()
    )

    first = chat_result(
        (
            "FST cao hay thấp phản ánh "
            "mối quan hệ di truyền như thế nào "
            "giữa các quần thể?"
        ),
        conversation_id=conversation_id,
    )

    if first.get("turn") != 1:
        raise RuntimeError(
            "recovery baseline turn is not 1"
        )

    print(
        "PASS persisted baseline turn"
    )

    compose(
        "restart",
        "postgres",
    )

    wait_service(
        "postgres"
    )

    compose(
        "restart",
        "chatbot",
    )

    wait_service(
        "chatbot"
    )

    second = chat_result(
        "Giải thích rõ hơn ý vừa rồi.",
        conversation_id=conversation_id,
    )

    if second.get("turn") != 2:
        raise RuntimeError(
            "conversation did not survive restart"
        )

    loaded = second.get(
        "history_turns_loaded"
    )

    if (
        not isinstance(loaded, int)
        or loaded < 1
    ):
        raise RuntimeError(
            "persisted history was not reloaded"
        )

    decision = second.get(
        "decision"
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise RuntimeError(
            "recovery decision missing"
        )

    if decision.get(
        "domain"
    ) != "in_domain":
        raise RuntimeError(
            "persisted context was not recovered"
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
            "follow-up was not resolved "
            "from persisted context"
        )

    print(
        "PASS conversation persisted "
        "across PostgreSQL restart"
    )

    print(
        "PASS history recovered "
        "after chatbot restart"
    )

    print()
    print(
        "PERSISTENT STATE RECOVERY "
        "ACCEPTANCE PASS"
    )
