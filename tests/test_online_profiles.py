"""Online accelerator profile execution tests.

Pins the compose-file selection and GPU-offload environment injection that
``scripts/accelerator.sh online`` applies for the CPU and GPU online profiles.
The offline profile matrix is covered by ``tests/test_offline_installer.py``;
``tests/test_accelerator.py`` covers accelerator *resolution*. These tests cover
the online *execution* path without a live Docker daemon or GPU hardware.
"""

from __future__ import annotations

import ast
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "accelerator.sh"

ENV_VARS = ("LLAMA_GPU_LAYERS", "LLAMA_GPU_LAYERS_DRAFT", "EMBEDDING_GPU_LAYERS")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _prepare_fake_bin(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    env_log = tmp_path / "env.log"

    _write_executable(
        fake_bin / "docker",
        f"""
        #!/usr/bin/env python3
        import os
        import shlex
        import sys
        from pathlib import Path

        args = sys.argv[1:]
        Path({str(docker_log)!r}).open("a", encoding="utf-8").write(
            "docker " + shlex.join(args) + "\\n"
        )
        if args[:1] == ["info"]:
            print('{{"nvidia": {{}}}}')
        elif args[:1] == ["compose"]:
            values = {{key: os.environ.get(key) for key in {ENV_VARS!r}}}
            Path({str(env_log)!r}).open("a", encoding="utf-8").write(
                repr(values) + "\\n"
            )
            print("NAME IMAGE STATUS")
        else:
            print("mock")
        """,
    )
    _write_executable(
        fake_bin / "nvidia-smi",
        """
        #!/usr/bin/env sh
        # gpu_host_ready runs `command -v nvidia-smi` and `nvidia-smi -L`.
        case "$*" in
          *-L*) echo "GPU 0: NVIDIA GeForce GTX 1660 Super (UUID: GPU-0)";;
          *) echo "OK";;
        esac
        exit 0
        """,
    )
    return fake_bin, docker_log, env_log


def _run_profile(
    tmp_path: Path, accelerator: str, action: str = "status"
) -> tuple[str, str, str]:
    fake_bin, docker_log, env_log = _prepare_fake_bin(tmp_path)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("LLAMA_", "EMBEDDING_"))
    }
    environment["PATH"] = f"{fake_bin}:{os.environ['PATH']}"
    environment["MOCK_DOCKER_LOG"] = str(docker_log)
    environment["MOCK_ENV_LOG"] = str(env_log)

    result = subprocess.run(
        ["bash", str(SCRIPT), "online", accelerator, action],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout, result.stderr, result.returncode


def test_online_cpu_profile_forces_zero_offload_and_omits_gpu_override(
    tmp_path: Path,
) -> None:
    stdout, stderr, returncode = _run_profile(tmp_path, "cpu")

    assert returncode == 0, stderr or stdout
    docker_log = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert "compose -f" in docker_log
    assert "docker-compose.yml" in docker_log
    assert "docker-compose.gpu.yml" not in docker_log
    env_log = (tmp_path / "env.log").read_text(encoding="utf-8")
    assert env_log.count("{") == 1, "expected exactly one compose invocation"
    values = ast.literal_eval(env_log.strip())
    assert values == {
        "LLAMA_GPU_LAYERS": "0",
        "LLAMA_GPU_LAYERS_DRAFT": "0",
        "EMBEDDING_GPU_LAYERS": "0",
    }


def test_online_gpu_profile_adds_gpu_override_and_does_not_force_offload(
    tmp_path: Path,
) -> None:
    stdout, stderr, returncode = _run_profile(tmp_path, "gpu")

    assert returncode == 0, stderr or stdout
    docker_log = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert "compose -f" in docker_log
    assert "docker-compose.yml" in docker_log
    assert "docker-compose.gpu.yml" in docker_log
    env_log = (tmp_path / "env.log").read_text(encoding="utf-8")
    assert env_log.count("{") == 1, "expected exactly one compose invocation"
    values = ast.literal_eval(env_log.strip())
    assert values == {
        "LLAMA_GPU_LAYERS": None,
        "LLAMA_GPU_LAYERS_DRAFT": None,
        "EMBEDDING_GPU_LAYERS": None,
    }


@pytest.mark.parametrize("accelerator", ["cpu", "gpu"])
def test_online_status_runs_single_compose_ps(tmp_path: Path, accelerator: str) -> None:
    _run_profile(tmp_path, accelerator)
    docker_log = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert docker_log.count(" compose ") == 1
    assert docker_log.rstrip().endswith(" ps")
