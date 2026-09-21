"""Concurrent authenticated streaming benchmark."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from concurrent.futures import (
    ThreadPoolExecutor,
)

from .client import (
    StreamResult,
    stream_once,
)
from .stream import DEFAULT_PROMPT


def percentile(
    values: list[float],
    percentile_value: float,
) -> float:
    ordered = sorted(values)

    index = max(
        0,
        min(
            len(ordered) - 1,
            math.ceil(
                percentile_value
                * len(ordered)
            )
            - 1,
        ),
    )

    return ordered[index]


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
        "--clients",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
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
        default=600,
    )

    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
    )


def one_round(
    *,
    clients: int,
    url: str,
    prompt: str,
    timeout: int,
) -> tuple[
    list[StreamResult],
    float,
]:
    started = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=clients
    ) as executor:
        futures = [
            executor.submit(
                stream_once,
                url,
                prompt,
                timeout=timeout,
            )
            for _ in range(clients)
        ]

        results = [
            future.result()
            for future in futures
        ]

    elapsed = (
        time.perf_counter()
        - started
    )

    return results, elapsed


def run(
    args: argparse.Namespace,
) -> None:
    if args.clients < 1:
        raise RuntimeError(
            "clients must be >= 1"
        )

    if args.rounds < 1:
        raise RuntimeError(
            "rounds must be >= 1"
        )

    url = (
        args.url.rstrip("/")
        + "/chat/stream"
    )

    for number in range(
        1,
        args.warmup + 1,
    ):
        _, elapsed = one_round(
            clients=args.clients,
            url=url,
            prompt=args.prompt,
            timeout=args.timeout,
        )

        print(
            f"warmup={number} "
            f"clients={args.clients} "
            f"wall={elapsed:.3f}s"
        )

        time.sleep(args.pause)

    all_results: list[
        StreamResult
    ] = []

    round_times: list[float] = []

    for number in range(
        1,
        args.rounds + 1,
    ):
        results, elapsed = one_round(
            clients=args.clients,
            url=url,
            prompt=args.prompt,
            timeout=args.timeout,
        )

        all_results.extend(results)
        round_times.append(elapsed)

        characters = sum(
            result.characters
            for result in results
        )

        print(
            f"round={number} "
            f"clients={args.clients} "
            f"wall={elapsed:.3f}s "
            f"chars={characters} "
            "aggregate_chars_per_second="
            f"{characters / elapsed:.1f}"
        )

        time.sleep(args.pause)

    total_characters = sum(
        result.characters
        for result in all_results
    )

    total_wall = sum(
        round_times
    )

    totals = [
        result.total
        for result in all_results
    ]

    summary = {
        "label": args.label,
        "clients": args.clients,
        "rounds": args.rounds,
        "requests": len(all_results),
        "median_ttft_seconds": (
            statistics.median(
                result.ttft
                for result in all_results
            )
        ),
        "median_total_seconds": (
            statistics.median(totals)
        ),
        "p95_total_seconds": percentile(
            totals,
            0.95,
        ),
        "median_request_chars_per_second": (
            statistics.median(
                result.chars_per_second
                for result in all_results
            )
        ),
        "median_round_wall_seconds": (
            statistics.median(
                round_times
            )
        ),
        "aggregate_chars_per_second": (
            total_characters
            / total_wall
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
