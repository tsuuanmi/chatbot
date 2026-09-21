"""Canonical offline release CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from .models import (
    build as build_models,
    verify as verify_models,
)
from .runtime import (
    build as build_runtime,
    verify as verify_runtime,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tools.release"
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    build_parser = commands.add_parser(
        "build"
    )

    build_parser.add_argument(
        "kind",
        choices=(
            "runtime",
            "models",
        ),
    )

    build_parser.add_argument(
        "--version",
    )

    build_parser.add_argument(
        "--dist",
        type=Path,
        default=Path("dist"),
    )

    verify_parser = commands.add_parser(
        "verify"
    )

    verify_parser.add_argument(
        "kind",
        choices=(
            "runtime",
            "models",
        ),
    )

    verify_parser.add_argument(
        "path",
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "build":
        if args.kind == "runtime":
            build_runtime(
                args.version,
                args.dist,
            )
        else:
            build_models(
                args.version,
                args.dist,
            )

        return

    if args.kind == "runtime":
        verify_runtime(
            args.path
        )
    else:
        verify_models(
            args.path
        )


if __name__ == "__main__":
    main()
