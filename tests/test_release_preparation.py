"""Release preparation tests for accelerator image packaging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _copy_release_source(destination: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".pi",
        "__pycache__",
        "*.pyc",
        "*.log",
        "databases",
        "runtime",
        "backups",
        "models",
    )
    shutil.copytree(ROOT, destination, ignore=ignored)


def _run(
    arguments: list[str], cwd: Path, environment: dict[str, str] | None = None
) -> None:
    subprocess.run(arguments, cwd=cwd, env=environment, check=True)


def test_prepare_packages_cpu_and_gpu_llama_images(tmp_path: Path) -> None:
    project = tmp_path / "project"
    _copy_release_source(project)
    _run(["git", "init"], project)
    _run(["git", "config", "user.email", "test@example.invalid"], project)
    _run(["git", "config", "user.name", "Test"], project)
    _run(["git", "add", "."], project)
    _run(["git", "commit", "-m", "test release"], project)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "docker.log"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'printf \'docker %s\\n\' "$*" >> "$MOCK_DOCKER_LOG"\n'
        'if [ "$1" = save ]; then\n'
        "  shift\n"
        '  [ "$1" = -o ]\n'
        '  : > "$2"\n'
        "fi\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    chatbot_zip = tmp_path / "chatbot.zip"
    images_zip = tmp_path / "images.zip"
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "MOCK_DOCKER_LOG": str(log),
    }
    _run(
        [
            "bash",
            "scripts/prepare.sh",
            "0.2.3",
            str(chatbot_zip),
            str(images_zip),
        ],
        project,
        environment,
    )

    extract = tmp_path / "extract"
    _run(["unzip", "-q", str(chatbot_zip), "-d", str(extract)], project)
    manifest = json.loads(
        (extract / "chatbotbca" / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["format_version"] == 6
    assert manifest["accelerator_images"] == {
        "cpu": "chatbot-bca/llama.cpp-server-cpu:991cf50e9eb",
        "gpu": "chatbot-bca/llama.cpp-server-cuda:b2497f8834f5",
    }
    assert set(manifest["accelerator_images"].values()) <= set(manifest["images"])
    assert (extract / "chatbotbca" / "docker-compose.offline.gpu.yml").is_file()
    assert (extract / "chatbotbca" / "scripts" / "accelerator.sh").is_file()
    docker_log = log.read_text(encoding="utf-8")
    assert docker_log.count("docker pull ghcr.io/ggml-org/llama.cpp:") == 2
    assert "llama.cpp-server-cpu:991cf50e9eb" in docker_log
    assert "llama.cpp-server-cuda:b2497f8834f5" in docker_log
