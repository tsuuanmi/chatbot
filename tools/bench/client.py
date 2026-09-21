"""Authenticated streaming benchmark client."""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass

from tools.http_client import json_headers


@dataclass(
    frozen=True,
    slots=True,
)
class StreamResult:
    ttft: float
    total: float
    chunks: int
    characters: int
    chars_per_second: float


def stream_once(
    url: str,
    prompt: str,
    *,
    timeout: int = 300,
) -> StreamResult:
    request = urllib.request.Request(
        url,
        data=json.dumps(
            {
                "query": prompt,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers=json_headers(),
        method="POST",
    )

    started = time.perf_counter()

    first_chunk_at: float | None = None
    chunks = 0
    characters = 0
    saw_start = False
    saw_end = False

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                f"unexpected status {response.status}"
            )

        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        if not content_type.startswith(
            "text/event-stream"
        ):
            raise RuntimeError(
                "unexpected content type "
                f"{content_type}"
            )

        for raw in response:
            line = raw.decode(
                "utf-8"
            ).strip()

            if not line.startswith("data:"):
                continue

            event = json.loads(
                line[5:].strip()
            )

            event_type = event.get("type")

            if event_type == "start":
                saw_start = True

            elif event_type == "chunk":
                content = str(
                    event.get(
                        "content",
                        "",
                    )
                )

                if not content:
                    continue

                if first_chunk_at is None:
                    first_chunk_at = (
                        time.perf_counter()
                    )

                chunks += 1
                characters += len(content)

            elif event_type == "end":
                saw_end = True

            elif event_type == "error":
                raise RuntimeError(
                    f"stream error: {event}"
                )

    finished = time.perf_counter()

    if not saw_start:
        raise RuntimeError(
            "missing start event"
        )

    if not saw_end:
        raise RuntimeError(
            "missing end event"
        )

    if first_chunk_at is None:
        raise RuntimeError(
            "stream produced no content"
        )

    ttft = (
        first_chunk_at - started
    )

    total = finished - started

    generation_time = max(
        total - ttft,
        0.000001,
    )

    return StreamResult(
        ttft=ttft,
        total=total,
        chunks=chunks,
        characters=characters,
        chars_per_second=(
            characters / generation_time
        ),
    )
