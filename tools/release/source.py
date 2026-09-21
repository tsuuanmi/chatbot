"""Release source-state helpers."""

from __future__ import annotations

import os
import platform
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(
    frozen=True,
    slots=True,
)
class Source:
    sha: str
    short_sha: str
    state: str
    architecture: str


def git(
    *args: str,
) -> str:
    return subprocess.run(
        [
            "git",
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout.strip()


def export_commit(
    sha: str,
    destination: Path,
) -> None:
    destination.mkdir(
        parents=True,
        exist_ok=False,
    )

    archive = (
        destination.parent
        / f".chatbot-source-{sha[:12]}.tar"
    )

    try:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                "-o",
                str(archive),
                sha,
            ],
            check=True,
        )

        with tarfile.open(
            archive,
            mode="r:",
        ) as source:
            members = source.getmembers()

            for member in members:
                member_path = PurePosixPath(
                    member.name
                )

                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                ):
                    raise RuntimeError(
                        "unsafe path in git archive: "
                        f"{member.name}"
                    )

            source.extractall(
                destination
            )

    finally:
        archive.unlink(
            missing_ok=True
        )
def inspect_source() -> Source:
    status = git(
        "status",
        "--porcelain",
        "--untracked-files=normal",
    )

    state = (
        "dirty"
        if status
        else "clean"
    )

    if (
        state == "dirty"
        and os.environ.get(
            "ALLOW_DIRTY_BUNDLE",
            "0",
        )
        != "1"
    ):
        raise RuntimeError(
            "refusing to build release artifact "
            "from a dirty working tree; "
            "commit changes first or use "
            "ALLOW_DIRTY_BUNDLE=1 for development"
        )

    return Source(
        sha=git(
            "rev-parse",
            "HEAD",
        ),
        short_sha=git(
            "rev-parse",
            "--short=12",
            "HEAD",
        ),
        state=state,
        architecture=platform.machine(),
    )
