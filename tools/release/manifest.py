"""Manifest and checksum helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path


def write_manifest(
    path: Path,
    values: dict[str, str],
) -> None:
    lines = [
        f"{key}={value}"
        for key, value in values.items()
    ]

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def read_manifest(
    path: Path,
) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(
            f"manifest is missing: {path}"
        )

    values: dict[str, str] = {}

    for raw in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw.strip()

        if not line:
            continue

        if "=" not in line:
            raise RuntimeError(
                f"invalid manifest line: {raw!r}"
            )

        key, value = line.split(
            "=",
            1,
        )

        values[key] = value

    return values


def digest(
    path: Path,
) -> str:
    hasher = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        while True:
            block = handle.read(
                1024 * 1024
            )

            if not block:
                break

            hasher.update(
                block
            )

    return hasher.hexdigest()


def write_checksums(
    root: Path,
) -> None:
    checksum_path = (
        root / "SHA256SUMS"
    )

    files = sorted(
        path
        for path in root.rglob("*")
        if (
            path.is_file()
            and path != checksum_path
        )
    )

    lines = [
        (
            f"{digest(path)}  "
            f"{path.relative_to(root)}"
        )
        for path in files
    ]

    checksum_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def verify_checksums(
    root: Path,
) -> None:
    checksum_path = (
        root / "SHA256SUMS"
    )

    if not checksum_path.is_file():
        raise RuntimeError(
            "SHA256SUMS is missing"
        )

    for raw in checksum_path.read_text(
        encoding="utf-8"
    ).splitlines():
        if not raw.strip():
            continue

        expected, separator, relative = (
            raw.partition("  ")
        )

        if not separator:
            raise RuntimeError(
                f"invalid checksum line: {raw!r}"
            )

        path = root / relative

        if not path.is_file():
            raise RuntimeError(
                f"checksummed file is missing: "
                f"{relative}"
            )

        actual = digest(
            path
        )

        if actual != expected:
            raise RuntimeError(
                f"checksum mismatch: {relative}"
            )

    print(
        "PASS artifact checksums"
    )
