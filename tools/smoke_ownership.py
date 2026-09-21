"""Verify authenticated conversation ownership isolation."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


BASE_URL = "http://127.0.0.1:1416"


def read_key(
    path: str,
) -> str:
    value = Path(path).read_text(
        encoding="utf-8"
    ).strip()

    if not value:
        raise RuntimeError(
            f"empty API key: {path}"
        )

    return value


KEY_A = read_key(
    "runtime/secrets/chat_api_key"
)

KEY_B = read_key(
    "runtime/secrets/chat_api_key_owner_b"
)


def chat(
    api_key: str,
    conversation_id: str,
    message: str,
) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{BASE_URL}/chat/run",
        data=json.dumps(
            {
                "message": message,
                "conversation_id": conversation_id,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                f"Bearer {api_key}"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=90,
        ) as response:
            return (
                response.status,
                json.load(response),
            )

    except urllib.error.HTTPError as error:
        raw = error.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            body = json.loads(
                raw
            )
        except json.JSONDecodeError:
            body = {
                "detail": raw,
            }

        return (
            error.code,
            body,
        )


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(
            message
        )


def main() -> None:
    conversation_a = str(
        uuid4()
    )

    conversation_b = str(
        uuid4()
    )

    status, body = chat(
        KEY_A,
        conversation_a,
        "FST cao hay thấp phản ánh mối quan hệ "
        "di truyền như thế nào giữa các quần thể?",
    )

    require(
        status == 200,
        f"owner A create failed: {status} {body}",
    )

    require(
        body["result"]["turn"] == 1,
        "owner A initial turn is not 1",
    )

    print(
        "PASS owner A creates conversation"
    )

    status, body = chat(
        KEY_B,
        conversation_a,
        "Giải thích rõ hơn.",
    )

    require(
        status == 404,
        (
            "owner B could access owner A conversation: "
            f"{status} {body}"
        ),
    )

    require(
        body.get("detail")
        == "Conversation not found",
        "foreign conversation leaked ownership details",
    )

    print(
        "PASS owner B cannot access owner A -> 404"
    )

    status, body = chat(
        KEY_B,
        conversation_b,
        "FST cao hay thấp phản ánh mối quan hệ "
        "di truyền như thế nào giữa các quần thể?",
    )

    require(
        status == 200,
        f"owner B create failed: {status} {body}",
    )

    require(
        body["result"]["turn"] == 1,
        "owner B initial turn is not 1",
    )

    print(
        "PASS owner B creates conversation"
    )

    status, body = chat(
        KEY_A,
        conversation_b,
        "Giải thích rõ hơn.",
    )

    require(
        status == 404,
        (
            "owner A could access owner B conversation: "
            f"{status} {body}"
        ),
    )

    print(
        "PASS owner A cannot access owner B -> 404"
    )

    status, body = chat(
        KEY_A,
        conversation_a,
        "Biểu đồ Venn thể hiện mối quan hệ gì "
        "giữa các vùng dữ liệu trong hệ thống giám định?",
    )

    require(
        status == 200,
        f"owner A continuation failed: {status} {body}",
    )

    require(
        body["result"]["turn"] == 2,
        "owner A continuation is not turn 2",
    )

    print(
        "PASS owner A retains own conversation"
    )

    status, body = chat(
        KEY_B,
        conversation_b,
        "Biểu đồ Venn thể hiện mối quan hệ gì "
        "giữa các vùng dữ liệu trong hệ thống giám định?",
    )

    require(
        status == 200,
        f"owner B continuation failed: {status} {body}",
    )

    require(
        body["result"]["turn"] == 2,
        "owner B continuation is not turn 2",
    )

    print(
        "PASS owner B retains own conversation"
    )

    print()
    print(
        "M6B OWNERSHIP SMOKE PASS"
    )


if __name__ == "__main__":
    main()
