"""Tests for the offline Ubuntu and RHEL host-platform gate."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "offline" / "host_platform.sh"


def _run_platform(tmp_path: Path, os_release: str) -> subprocess.CompletedProcess[str]:
    release_path = tmp_path / "os-release"
    release_path.write_text(os_release, encoding="utf-8")
    environment = os.environ | {"HOST_OS_RELEASE": str(release_path)}
    return subprocess.run(
        ["bash", "-c", 'source "$1"; host_platform', "bash", str(SCRIPT)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_host_platform_accepts_supported_ubuntu_and_rhel(tmp_path: Path) -> None:
    ubuntu_2204 = _run_platform(tmp_path, "ID=ubuntu\nVERSION_ID=22.04\n")
    ubuntu_2604 = _run_platform(tmp_path, "ID=ubuntu\nVERSION_ID=26.04\n")
    rhel = _run_platform(tmp_path, "ID=rhel\nVERSION_ID=8.10\n")

    assert ubuntu_2204.returncode == 0
    assert ubuntu_2204.stdout == "ubuntu\n"
    assert ubuntu_2604.returncode == 0
    assert ubuntu_2604.stdout == "ubuntu\n"
    assert rhel.returncode == 0
    assert rhel.stdout == "rhel\n"


def test_host_platform_rejects_unsupported_distribution(tmp_path: Path) -> None:
    result = _run_platform(tmp_path, "ID=rocky\nVERSION_ID=8.10\n")

    assert result.returncode != 0
    assert "Unsupported target operating system" in result.stderr


def test_rhel_requires_enforcing_selinux(tmp_path: Path) -> None:
    release_path = tmp_path / "os-release"
    release_path.write_text("ID=rhel\nVERSION_ID=8.10\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    getenforce = fake_bin / "getenforce"
    getenforce.write_text(
        "#!/usr/bin/env sh\nprintf 'Permissive\\n'\n", encoding="utf-8"
    )
    getenforce.chmod(0o755)
    environment = os.environ | {
        "HOST_OS_RELEASE": str(release_path),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; validate_host_platform rhel',
            "bash",
            str(SCRIPT),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "SELinux Enforcing" in result.stderr


def test_offline_host_requires_python_39_or_newer(tmp_path: Path) -> None:
    release_path = tmp_path / "os-release"
    release_path.write_text("ID=ubuntu\nVERSION_ID=26.04\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python = fake_bin / "python3"
    python.write_text("#!/usr/bin/env sh\nexit 1\n", encoding="utf-8")
    python.chmod(0o755)
    environment = os.environ | {
        "HOST_OS_RELEASE": str(release_path),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; validate_host_platform ubuntu',
            "bash",
            str(SCRIPT),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Python 3.9 or newer" in result.stderr


def test_compose_files_label_rhel_bind_mounts() -> None:
    offline = (ROOT / "compose" / "docker-compose.offline.yml").read_text(
        encoding="utf-8"
    )
    online = (ROOT / "compose" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "${MODEL_DIR:?Set MODEL_DIR}:/models:ro,z" in offline
    assert "${RUNTIME_DIR:?Set RUNTIME_DIR}/chromadb:/data:Z" in offline
    assert "${CONFIG_DIR:?Set CONFIG_DIR}/auth:/run/secrets:ro,Z" in offline
    assert (
        "${CONFIG_DIR:?Set CONFIG_DIR}/nginx.conf:/etc/nginx/nginx.conf:ro,Z" in offline
    )
    assert "./models:/models:ro,z" in online
    assert "./databases/chromadb:/data:Z" in online
    assert "./data/figures:/app/data/figures:ro,Z" in online
