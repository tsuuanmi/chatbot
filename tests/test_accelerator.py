"""Tests for accelerator-profile selection without Docker hardware."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "accelerator.sh"
OFFLINE_COMPOSE = ROOT / "docker-compose.offline.yml"


def test_cpu_resolution_never_invokes_nvidia_tools(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "nvidia-called"
    nvidia = fake_bin / "nvidia-smi"
    nvidia.write_text(f"#!/bin/sh\ntouch {marker}\nexit 42\n", encoding="utf-8")
    nvidia.chmod(0o755)

    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", str(SCRIPT), "resolve", "cpu"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "cpu\n"
    assert not marker.exists()


def test_offline_cpu_profile_defaults_to_zero_offload() -> None:
    compose = OFFLINE_COMPOSE.read_text(encoding="utf-8")

    assert "--n-gpu-layers ${LLAMA_GPU_LAYERS:-0}" in compose
    assert "--n-gpu-layers ${EMBEDDING_GPU_LAYERS:-0}" in compose


def test_invalid_accelerator_is_rejected() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "resolve", "invalid"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "ACCELERATOR must be auto, cpu, or gpu" in result.stderr
