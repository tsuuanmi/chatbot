"""Canonical benchmark CLI."""

from __future__ import annotations

import argparse

from . import (
    concurrency,
    stream,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tools.bench"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    stream_parser = commands.add_parser(
        "stream",
        help="Benchmark sequential SSE generation",
    )

    stream.configure(
        stream_parser
    )

    concurrency_parser = (
        commands.add_parser(
            "concurrency",
            help=(
                "Benchmark concurrent "
                "SSE requests"
            ),
        )
    )

    concurrency.configure(
        concurrency_parser
    )

    args = parser.parse_args()

    if args.command == "stream":
        stream.run(args)
        return

    if args.command == "concurrency":
        concurrency.run(args)
        return

    raise RuntimeError(
        f"unsupported command: {args.command}"
    )


if __name__ == "__main__":
    main()
