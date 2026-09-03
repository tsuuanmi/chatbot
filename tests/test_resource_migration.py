"""Tests for the isolated explicit Docker resource migration utility."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "offline" / "migrate_resources.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _prepare_docker(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "docker.log"
    _write_executable(
        fake_bin / "docker",
        """
        #!/usr/bin/env sh
        printf 'docker %s\\n' "$*" >> "$MOCK_DOCKER_LOG"
        """,
    )
    return fake_bin, log


def _run(
    tmp_path: Path, *arguments: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_bin, log = _prepare_docker(tmp_path)
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MOCK_DOCKER_LOG": str(log),
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log


def test_migration_requires_explicit_confirmation(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "--container", "old-container")

    assert result.returncode != 0
    assert "--confirm" in result.stderr
    assert not log.exists()


def test_migration_removes_only_explicit_resources(tmp_path: Path) -> None:
    result, log_path = _run(
        tmp_path,
        "--confirm",
        "--container",
        "old-container",
        "--container",
        "old-second",
        "--volume",
        "old-volume",
    )

    assert result.returncode == 0, result.stderr
    log = log_path.read_text(encoding="utf-8")
    assert log.splitlines() == [
        "docker rm -f old-container old-second",
        "docker volume rm old-volume",
    ]


def test_migration_rejects_wildcards(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "--confirm", "--container", "*")

    assert result.returncode != 0
    assert "Invalid Docker resource name or ID" in result.stderr
    assert not log.exists()
