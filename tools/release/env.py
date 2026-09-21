"""Environment-file parsing."""

from __future__ import annotations

from pathlib import Path


def read_env(
    *paths: Path,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for path in paths:
        if not path.is_file():
            raise RuntimeError(
                f"environment file is missing: {path}"
            )

        for raw in path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = raw.strip()

            if (
                not line
                or line.startswith("#")
            ):
                continue

            if "=" not in line:
                raise RuntimeError(
                    f"invalid environment line "
                    f"in {path}: {raw!r}"
                )

            key, value = line.split(
                "=",
                1,
            )

            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {'"', "'"}
            ):
                value = value[1:-1]

            values[key] = value

    return values


def require(
    values: dict[str, str],
    *names: str,
) -> None:
    missing = [
        name
        for name in names
        if not values.get(
            name,
            ""
        ).strip()
    ]

    if missing:
        raise RuntimeError(
            "required configuration missing: "
            + ", ".join(missing)
        )
