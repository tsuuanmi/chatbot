"""Single-request streaming benchmark."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time

from .client import (
    StreamResult,
    stream_once,
)


DEFAULT_PROMPT = (
    "Giải thích khái niệm heterozygosity "
    "trong di truyền quần thể."
)


def median(
    results: list[StreamResult],
    field: str,
) -> float:
    return statistics.median(
        float(
            getattr(result, field)
        )
        for result in results
    )


def configure(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--label",
        required=True,
    )

    parser.add_argument(
        "--url",
        default=os.environ.get(
            "GATEWAY_URL",
            "http://127.0.0.1:18080",
        ),
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--pause",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
    )

    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
    )


def run(
    args: argparse.Namespace,
) -> None:
    if args.runs < 1:
        raise RuntimeError(
            "runs must be >= 1"
        )

    url = (
        args.url.rstrip("/")
        + "/api/v1/chat/stream"
    )

    for number in range(
        1,
        args.warmup + 1,
    ):
        result = stream_once(
            url,
            args.prompt,
            timeout=args.timeout,
        )

        print(
            f"warmup={number} "
            f"ttft={result.ttft:.3f}s "
            f"total={result.total:.3f}s "
            f"chunks={result.chunks}"
        )

        time.sleep(args.pause)

    results: list[
        StreamResult
    ] = []

    for number in range(
        1,
        args.runs + 1,
    ):
        result = stream_once(
            url,
            args.prompt,
            timeout=args.timeout,
        )

        results.append(result)

        print(
            f"run={number} "
            f"ttft={result.ttft:.3f}s "
            f"total={result.total:.3f}s "
            f"chunks={result.chunks} "
            f"chars={result.characters} "
            "chars_per_second="
            f"{result.chars_per_second:.1f}"
        )

        time.sleep(args.pause)

    summary = {
        "label": args.label,
        "runs": args.runs,
        "median_ttft_seconds": median(
            results,
            "ttft",
        ),
        "median_total_seconds": median(
            results,
            "total",
        ),
        "mean_total_seconds": (
            statistics.mean(
                result.total
                for result in results
            )
        ),
        "median_chars_per_second": (
            median(
                results,
                "chars_per_second",
            )
        ),
        "median_chunks": median(
            results,
            "chunks",
        ),
        "median_characters": median(
            results,
            "characters",
        ),
    }

    print()
    print(
        "RESULT "
        + json.dumps(
            summary,
            sort_keys=True,
        )
    )
