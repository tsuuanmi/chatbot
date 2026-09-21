"""Configured figure and raw image acceptance."""

from __future__ import annotations

import base64
import unicodedata
from pathlib import Path
from uuid import uuid4

from .client import (
    chat_result,
    expect_status,
    json_body,
    request,
    require_stream,
    stream_events,
)
from .config import (
    GATEWAY_URL,
    RUNTIME_ENV,
)
from .proc import compose


FIGURE_ID = "heatmap1"

VISION_QUERY = (
    "FST có ý nghĩa gì trong di truyền quần thể? "
    "Hãy quan sát trực tiếp ảnh được cung cấp và "
    "liệt kê chính xác tất cả nhãn quần thể "
    "xuất hiện trên hai trục."
)

EXPECTED_PIXEL_LABELS = (
    "aa",
    "cauc",
    "hisp",
    "asian",
    "viet nam",
)


def _runtime_env() -> dict[str, str]:
    path = Path(RUNTIME_ENV)

    values: dict[str, str] = {}

    for raw in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split(
            "=",
            1,
        )

        values[
            key.strip()
        ] = value.strip().strip(
            "\"'"
        )

    return values


def _figure_path() -> Path:
    values = _runtime_env()

    figure_dir = Path(
        values.get(
            "FIGURE_DIR",
            "data/figures",
        )
    ).expanduser()

    if not figure_dir.is_absolute():
        figure_dir = (
            Path.cwd()
            / figure_dir
        )

    path = (
        figure_dir
        / f"{FIGURE_ID}.png"
    )

    if not path.is_file():
        raise RuntimeError(
            "acceptance figure is missing: "
            f"{path}"
        )

    return path


def _image_data_url() -> str:
    raw = _figure_path().read_bytes()

    return (
        "data:image/png;base64,"
        + base64.b64encode(
            raw
        ).decode("ascii")
    )


def _result(
    raw: bytes,
) -> dict[str, object]:
    return json_body(raw)


def _decision(
    result: dict[str, object],
) -> dict[str, object]:
    value = result.get(
        "decision"
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "chat response has no decision object"
        )

    return value


def _fold(
    text: str,
) -> str:
    normalized = (
        unicodedata.normalize(
            "NFKD",
            text,
        )
    )

    folded = "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    )

    return (
        folded
        .replace("đ", "d")
        .replace("Đ", "D")
        .lower()
    )


def _require_pixel_labels(
    answer: str,
) -> None:
    folded = _fold(
        answer
    )

    missing = [
        label
        for label
        in EXPECTED_PIXEL_LABELS
        if label not in folded
    ]

    if missing:
        raise RuntimeError(
            "vision response is missing "
            "pixel-only labels: "
            + ", ".join(missing)
        )


def _require_generated(
    result: dict[str, object],
) -> None:
    if result.get(
        "source"
    ) != "generated":
        raise RuntimeError(
            "image request did not use "
            "generated source"
        )

    decision = _decision(
        result
    )

    if decision.get(
        "domain"
    ) != "in_domain":
        raise RuntimeError(
            "image request was not in-domain"
        )

    if decision.get(
        "risk"
    ) != "standard":
        raise RuntimeError(
            "standard image request changed risk"
        )


def _persistence_check(
    conversation_id: str,
    expected_query: str,
) -> None:
    code = "\n".join(
        [
            "import psycopg",
            (
                "from chatbot_app.database "
                "import postgres_connection_string"
            ),
            (
                "conversation_id = "
                + repr(conversation_id)
            ),
            (
                "expected_query = "
                + repr(expected_query)
            ),
            (
                "connection = psycopg.connect("
                "postgres_connection_string(), "
                "autocommit=True)"
            ),
            "try:",
            "    row = connection.execute(",
            (
                "        \"SELECT query FROM "
                "conversation_turns "
                "WHERE conversation_id = %s::uuid "
                "ORDER BY turn DESC LIMIT 1\","
            ),
            "        (conversation_id,),",
            "    ).fetchone()",
            "    if row is None:",
            (
                "        raise RuntimeError("
                "\"media conversation was not persisted\")"
            ),
            "    query = row[0]",
            "    if query != expected_query:",
            (
                "        raise RuntimeError("
                "\"persisted query changed\")"
            ),
            "    if \"data:image\" in query:",
            (
                "        raise RuntimeError("
                "\"data URL persisted in query\")"
            ),
            "    if \"base64,\" in query:",
            (
                "        raise RuntimeError("
                "\"base64 marker persisted in query\")"
            ),
            (
                "    print("
                "\"MEDIA PERSISTENCE ACCEPTANCE PASS\")"
            ),
            "finally:",
            "    connection.execute(",
            (
                "        \"DELETE FROM conversations "
                "WHERE id = %s::uuid\","
            ),
            "        (conversation_id,),",
            "    )",
            "    connection.close()",
        ]
    )

    compose(
        "exec",
        "-T",
        "chatbot",
        "python",
        "-c",
        code,
    )


def media_quick_suite() -> None:
    image = _image_data_url()

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "Giải thích hình này",
            "figure_id": "does-not-exist",
        },
        authenticated=True,
    )

    expect_status(
        "unknown figure",
        status,
        422,
    )

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "FST có ý nghĩa gì trong "
                "di truyền quần thể?"
            ),
            "image": "%%%not-base64%%%",
        },
        authenticated=True,
    )

    expect_status(
        "malformed base64",
        status,
        422,
    )

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "Giải thích hình này",
            "figure_id": FIGURE_ID,
            "image": image,
        },
        authenticated=True,
    )

    expect_status(
        "figure and image conflict",
        status,
        422,
    )

    status, _, raw = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "Cách nấu phở bò ngon?",
            "image": image,
        },
        authenticated=True,
    )

    expect_status(
        "image out-of-domain request",
        status,
        200,
    )

    result = _result(
        raw
    )

    decision = _decision(
        result
    )

    if decision.get(
        "domain"
    ) != "out_of_domain":
        raise RuntimeError(
            "image bypassed out-of-domain policy"
        )

    if result.get(
        "source"
    ) != "out_of_domain":
        raise RuntimeError(
            "unexpected OOD image response source"
        )

    print(
        "PASS image does not bypass "
        "out-of-domain policy"
    )

    status, _, raw = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "Hãy kết luận mẫu hiện trường này "
                "có thuộc về nghi phạm hay không."
            ),
            "image": image,
        },
        authenticated=True,
    )

    expect_status(
        "image high-risk request",
        status,
        200,
    )

    result = _result(
        raw
    )

    decision = _decision(
        result
    )

    if decision.get(
        "risk"
    ) != "high":
        raise RuntimeError(
            "image bypassed high-risk policy"
        )

    if result.get(
        "source"
    ) != "evidence_limitation":
        raise RuntimeError(
            "unexpected high-risk image source"
        )

    print(
        "PASS image does not bypass "
        "high-risk policy"
    )

    direct = chat_result(
        "Giải thích hình này",
        figure_id=FIGURE_ID,
        base_url=GATEWAY_URL,
    )

    if direct.get(
        "source"
    ) != "figure_prepared":
        raise RuntimeError(
            "configured figure fast path failed"
        )

    if direct.get(
        "figure_id"
    ) != FIGURE_ID:
        raise RuntimeError(
            "configured figure ID was not returned"
        )

    if direct.get(
        "citations"
    ) != []:
        raise RuntimeError(
            "configured direct figure "
            "unexpectedly returned citations"
        )

    print(
        "PASS configured figure fast path"
    )

    events = stream_events(
        "Giải thích hình này",
        figure_id=FIGURE_ID,
        base_url=GATEWAY_URL,
    )

    _, end = require_stream(
        events
    )

    if end.get(
        "source"
    ) != "figure_prepared":
        raise RuntimeError(
            "streaming configured figure "
            "missed fast path"
        )

    if end.get(
        "citations"
    ) != []:
        raise RuntimeError(
            "streaming configured figure "
            "unexpectedly returned citations"
        )

    print(
        "MEDIA QUICK ACCEPTANCE PASS"
    )


def media_full_suite() -> None:
    image = _image_data_url()

    conversation_id = str(
        uuid4()
    )

    result = chat_result(
        VISION_QUERY,
        conversation_id=conversation_id,
        image=image,
        base_url=GATEWAY_URL,
    )

    _persistence_check(
        conversation_id,
        VISION_QUERY,
    )

    _require_generated(
        result
    )

    answer = str(
        result.get(
            "answer"
        )
        or ""
    )

    _require_pixel_labels(
        answer
    )

    print(
        "PASS gateway base64 pixel vision"
    )

    events = stream_events(
        VISION_QUERY,
        image=image,
        base_url=GATEWAY_URL,
    )

    answer, end = require_stream(
        events
    )

    _require_pixel_labels(
        answer
    )

    if end.get(
        "source"
    ) != "generated":
        raise RuntimeError(
            "streaming image source "
            "was not generated"
        )

    decision = end.get(
        "decision"
    )

    if not isinstance(
        decision,
        dict,
    ):
        raise RuntimeError(
            "streaming image decision missing"
        )

    if decision.get(
        "domain"
    ) != "in_domain":
        raise RuntimeError(
            "streaming image request "
            "was not in-domain"
        )

    print(
        "PASS streaming base64 pixel vision"
    )

    print(
        "MEDIA FULL ACCEPTANCE PASS"
    )
