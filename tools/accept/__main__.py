"""Canonical acceptance CLI."""

from __future__ import annotations

import argparse

from .suite import (
    full,
    recovery,
    verify,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tools.accept"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser(
        "verify",
        help="Run normal runtime acceptance",
    )

    commands.add_parser(
        "recovery",
        help=(
            "Verify persistent state "
            "across service restarts"
        ),
    )

    full_parser = commands.add_parser(
        "full",
        help="Run full release acceptance",
    )

    full_parser.add_argument(
        "--gpu",
        action="store_true",
        help="Include NVIDIA runtime acceptance",
    )

    args = parser.parse_args()

    if args.command == "verify":
        verify()
        return

    if args.command == "recovery":
        recovery()
        return

    if args.command == "full":
        full(
            gpu=args.gpu,
        )
        return

    raise RuntimeError(
        f"unsupported command: {args.command}"
    )


if __name__ == "__main__":
    main()
