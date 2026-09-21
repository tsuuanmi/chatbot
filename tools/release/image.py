"""Docker image helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def docker(
    *args: str,
) -> None:
    subprocess.run(
        [
            "docker",
            *args,
        ],
        check=True,
    )


def build(
    image: str,
    context: Path,
    *,
    build_args: dict[str, str],
    labels: dict[str, str] | None = None,
) -> None:
    arguments = [
        "build",
    ]

    for key, value in sorted(
        build_args.items()
    ):
        arguments.extend(
            [
                "--build-arg",
                f"{key}={value}",
            ]
        )

    for key, value in sorted(
        (labels or {}).items()
    ):
        arguments.extend(
            [
                "--label",
                f"{key}={value}",
            ]
        )

    arguments.extend(
        [
            "-t",
            image,
            str(context),
        ]
    )

    docker(*arguments)


def inspect_label(
    image: str,
    label: str,
) -> str:
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            '{{ index .Config.Labels "'
            + label
            + '" }}',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()

    if result == "<no value>":
        return ""

    return result
def require_image(
    image: str,
) -> None:
    subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            image,
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )


def tag(
    source: str,
    target: str,
) -> None:
    docker(
        "tag",
        source,
        target,
    )


def save(
    image: str,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    docker(
        "save",
        "-o",
        str(path),
        image,
    )
