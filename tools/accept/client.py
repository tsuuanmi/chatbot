"""HTTP helpers for runtime acceptance."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from tools.http_client import json_headers

from .config import INTERNAL_URL


def _uses_public_api(
    base_url: str,
) -> bool:
    return (
        base_url.rstrip("/")
        != INTERNAL_URL.rstrip("/")
    )


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
    authenticated: bool = False,
    extra_headers: dict[str, str] | None = None,
    timeout: int = 120,
) -> tuple[
    int,
    object,
    bytes,
]:
    headers: dict[str, str] = {}

    if body is not None:
        headers[
            "Content-Type"
        ] = "application/json"

    if authenticated:
        headers.update(
            json_headers()
        )

    if extra_headers:
        headers.update(
            extra_headers
        )

    wire_body = body

    # Stable public API uses "query".
    # Internal Hayhooks endpoints keep "message".
    if (
        body is not None
        and path in {
            "/api/v1/chat",
            "/api/v1/chat/stream",
        }
        and "message" in body
        and "query" not in body
    ):
        wire_body = dict(body)
        wire_body["query"] = wire_body.pop(
            "message"
        )

    data = (
        json.dumps(
            wire_body,
            ensure_ascii=False,
        ).encode(
            "utf-8"
        )
        if wire_body is not None
        else None
    )

    req = urllib.request.Request(
        base_url.rstrip("/")
        + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=timeout,
        ) as response:
            raw = response.read()

            return (
                response.status,
                response.headers,
                raw,
            )

    except urllib.error.HTTPError as error:
        raw = error.read()

        return (
            error.code,
            error.headers,
            raw,
        )


def json_body(
    raw: bytes,
) -> dict[str, object]:
    if not raw:
        return {}

    value = json.loads(
        raw.decode(
            "utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise RuntimeError(
            "response is not a JSON object"
        )

    return value


def expect_status(
    label: str,
    actual: int,
    expected: int,
) -> None:
    if actual != expected:
        raise RuntimeError(
            f"{label}: expected HTTP "
            f"{expected}, got {actual}"
        )

    print(
        f"PASS {label} -> {actual}"
    )


def chat_result(
    message: str,
    *,
    conversation_id: str | None = None,
    figure_id: str | None = None,
    image: str | None = None,
    base_url: str = INTERNAL_URL,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "message": message,
    }

    if conversation_id is not None:
        payload[
            "conversation_id"
        ] = conversation_id

    if figure_id is not None:
        payload[
            "figure_id"
        ] = figure_id

    if image is not None:
        payload[
            "image"
        ] = image

    public_api = _uses_public_api(
        base_url
    )

    status, _, raw = request(
        base_url,
        (
            "/api/v1/chat"
            if public_api
            else "/chat/run"
        ),
        method="POST",
        body=payload,
        authenticated=True,
        timeout=180,
    )

    expect_status(
        "authenticated chat",
        status,
        200,
    )

    body = json_body(
        raw
    )

    if public_api:
        return body

    result = body.get(
        "result"
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "chat response has no result object"
        )

    return result


def stream_events(
    message: str,
    *,
    conversation_id: str | None = None,
    figure_id: str | None = None,
    image: str | None = None,
    base_url: str = INTERNAL_URL,
) -> list[dict[str, object]]:
    public_api = _uses_public_api(
        base_url
    )

    payload: dict[str, object] = {
        (
            "query"
            if public_api
            else "message"
        ): message,
    }

    if conversation_id is not None:
        payload[
            "conversation_id"
        ] = conversation_id

    if figure_id is not None:
        payload[
            "figure_id"
        ] = figure_id

    if image is not None:
        payload[
            "image"
        ] = image

    stream_path = (
        "/api/v1/chat/stream"
        if public_api
        else "/chat/stream"
    )

    req = urllib.request.Request(
        base_url.rstrip("/")
        + stream_path,
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode(
            "utf-8"
        ),
        headers=json_headers(),
        method="POST",
    )

    events: list[
        dict[str, object]
    ] = []

    with urllib.request.urlopen(
        req,
        timeout=240,
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                "stream returned HTTP "
                f"{response.status}"
            )

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            )
        )

        if not content_type.startswith(
            "text/event-stream"
        ):
            raise RuntimeError(
                "unexpected stream content type: "
                f"{content_type}"
            )

        for raw in response:
            line = raw.decode(
                "utf-8"
            ).strip()

            if not line.startswith(
                "data:"
            ):
                continue

            event = json.loads(
                line[5:].strip()
            )

            if not isinstance(
                event,
                dict,
            ):
                raise RuntimeError(
                    "invalid SSE event"
                )

            events.append(
                event
            )

    return events


def require_stream(
    events: list[
        dict[str, object]
    ],
) -> tuple[
    str,
    dict[str, object],
]:
    types = [
        event.get(
            "type"
        )
        for event in events
    ]

    if (
        not types
        or types[0] != "start"
    ):
        raise RuntimeError(
            f"missing start event: {types}"
        )

    if "error" in types:
        raise RuntimeError(
            f"stream returned error: {events}"
        )

    chunks = [
        str(
            event.get(
                "content",
                "",
            )
        )
        for event in events
        if event.get(
            "type"
        )
        == "chunk"
    ]

    answer = "".join(
        chunks
    )

    if not answer.strip():
        raise RuntimeError(
            "stream produced no answer"
        )

    end_events = [
        event
        for event in events
        if event.get(
            "type"
        )
        == "end"
    ]

    if len(end_events) != 1:
        raise RuntimeError(
            "stream must contain exactly "
            "one end event"
        )

    return (
        answer,
        end_events[0],
    )
