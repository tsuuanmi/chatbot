"""Safe end-to-end tests for the offline installer control flow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
MODEL_NAMES = (
    "gemma-4-E2B-it-Q4_K_M.gguf",
    "mmproj-gemma-4-E2B-it-bf16.gguf",
    "mtp-gemma-4-E2B-it.gguf",
    "embeddinggemma-300M-Q8_0.gguf",
)
EXPECTED_REMOVAL_COMMAND = "docker rm -f current-labeled"
EXPECTED_VOLUME_REMOVAL_COMMAND = "docker volume rm chatbot-current-data"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _prepare_release(tmp_path: Path) -> Path:
    release = tmp_path / "chatbot"
    for directory in (
        release / "config",
        release / "images",
        release / "models",
        release / "scripts/offline",
        release / "compose",
    ):
        directory.mkdir(parents=True)

    source_files = (
        "compose/docker-compose.offline.yml",
        "compose/docker-compose.offline.gpu.yml",
        "scripts/accelerator.sh",
        "config/offline.env.template",
        "scripts/offline/common.sh",
        "scripts/offline/configure_host.sh",
        "scripts/offline/migrate_resources.sh",
        "scripts/offline/host_platform.sh",
        "scripts/offline/detect_network.py",
        "scripts/offline/manage_client.sh",
    )
    shutil.copy2(ROOT / "scripts/setup.sh", release / "setup.sh")
    for relative_path in source_files:
        destination = release / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, destination)

    (release / "images/runtime-images.tar").write_bytes(b"mock image archive")
    for model_name in MODEL_NAMES:
        (release / "models" / model_name).write_bytes(b"mock model")
    model_checksum_lines = [
        f"{hashlib.sha256((release / 'models' / name).read_bytes()).hexdigest()}  {name}"
        for name in MODEL_NAMES
    ]
    (release / "models" / "SHA256SUMS").write_text(
        "\n".join(model_checksum_lines) + "\n", encoding="utf-8"
    )

    manifest = {
        "format_version": 7,
        "architecture": "x86_64",
        "app_image": "chatbot:0.2.3",
        "accelerator_images": {
            "cpu": "chatbot/llama.cpp-server-cpu:test",
            "gpu": "chatbot/llama.cpp-server-cuda:test",
        },
        "images": [
            "chatbot:0.2.3",
            "chatbot/llama.cpp-server-cpu:test",
            "chatbot/llama.cpp-server-cuda:test",
            "chatbot/postgres:test",
            "chatbot/chromadb:test",
            "chatbot/nginx:test",
        ],
        "runtime_images_sha256": hashlib.sha256(
            (release / "images/runtime-images.tar").read_bytes()
        ).hexdigest(),
    }
    (release / "release-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    checksum_paths = [
        release / "setup.sh",
        release / "compose/docker-compose.offline.yml",
        release / "release-manifest.json",
        *(release / relative_path for relative_path in source_files[1:]),
    ]
    checksum_lines = []
    for path in checksum_paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_lines.append(f"{digest}  {path.relative_to(release)}")
    (release / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return release


def _prepare_fake_commands(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    command_log = tmp_path / "commands.log"
    mock_root = tmp_path / "host-root"
    mock_root.mkdir()

    _write_executable(
        fake_bin / "docker",
        r"""
        #!/usr/bin/env python3
        import os
        import shlex
        import sys
        from pathlib import Path

        args = sys.argv[1:]
        Path(os.environ["MOCK_COMMAND_LOG"]).open("a", encoding="utf-8").write(
            "docker " + shlex.join(args) + "\n"
        )
        if args[:2] == ["compose", "version"]:
            print("Docker Compose version mock")
        elif args and args[0] == "compose":
            commands = {"config", "down", "logs", "ps", "run", "stop", "up"}
            command_index = next(
                (index for index, value in enumerate(args) if value in commands), None
            )
            if command_index is None:
                raise SystemExit(2)
            command = args[command_index]
            remaining = args[command_index + 1 :]
            if command == "ps" and "-q" in remaining:
                print(f"mock-{remaining[-1]}")
            elif command == "run" and "indexer" in remaining:
                print("Mock indexer completed")
            elif (
                command == "up"
                and "proxy" in remaining
                and os.environ.get("MOCK_CHATBOT_UP_FAIL") == "1"
            ):
                raise SystemExit(42)
            elif command == "logs":
                print("mock chatbot database authentication failure")
        elif args and args[0] == "info":
            print('{"nvidia": {}}' if os.environ.get("MOCK_NVIDIA_RUNTIME", "1") == "1" else "{}")
        elif args[:2] == ["ps", "-aq"]:
            if os.environ.get("MOCK_DOCKER_PS_FAIL") == "1":
                raise SystemExit(42)
            print(
                "chatbot\n"
                "chatbot-postgres\n"
                "llama-server\n"
                "embedding-server\n"
                "chatbot-chromadb\n"
                "Chatbot-uppercase\n"
                "camofox-browser\n"
                "unrelated-project-worker\n"
                "current-labeled"
            )
        elif args and args[0] == "inspect":
            target = args[-1]
            format_value = args[args.index("--format") + 1]
            if (
                "State.Health" in format_value
                and target == "mock-chatbot"
                and os.environ.get("MOCK_CHATBOT_UNHEALTHY") == "1"
            ):
                print("unhealthy")
            elif "RestartPolicy" in format_value:
                print("unless-stopped")
            elif format_value == "{{.Name}}":
                print(f"/{target}")
            elif "com.docker.compose.project" in format_value:
                if target == "current-labeled":
                    print(os.environ["MOCK_CHATBOT_PROJECT_NAME"])
                elif target == "unrelated-project-worker":
                    print("other-project")
            elif ".Mounts" in format_value:
                if target == "chatbot-postgres":
                    print("chatbot-postgres-data")
            else:
                print("healthy")
        elif args and args[0] == "volume":
            if args[1] == "ls":
                print(
                    "chatbot-postgres-data\n"
                    "chatbot-current-data\n"
                    "generic-project-volume\n"
                    "unrelated-volume"
                )
            elif args[1] == "inspect":
                target = args[-1]
                if target == "chatbot-current-data":
                    print(os.environ["MOCK_CHATBOT_PROJECT_NAME"])
                elif target == "generic-project-volume":
                    print("other-project")
                elif target == "unrelated-volume":
                    print("camofox")
            elif args[1] != "rm":
                raise SystemExit(f"unsupported mock docker volume command: {args}")
        elif args[:2] == ["image", "inspect"]:
            pass
        elif args and args[0] == "run":
            if os.environ.get("MOCK_CUDA_UNAVAILABLE") == "1":
                raise SystemExit(42)
            print("  CUDA")
        elif args and args[0] in {"load", "rm", "stop", "update"}:
            pass
        else:
            raise SystemExit(f"unsupported mock docker command: {args}")
        """,
    )
    _write_executable(
        fake_bin / "ip",
        r"""
        #!/usr/bin/env python3
        import json
        import sys

        if "route" in sys.argv:
            print(json.dumps([{"dev": "eno1", "prefsrc": "192.168.50.10"}]))
        else:
            print(json.dumps([{
                "ifname": "eno1",
                "flags": ["UP", "LOWER_UP"],
                "operstate": "UP",
                "addr_info": [{
                    "family": "inet",
                    "local": "192.168.50.10",
                    "prefixlen": 24,
                    "scope": "global"
                }]
            }]))
        """,
    )
    _write_executable(
        fake_bin / "nvidia-smi",
        r"""
        #!/usr/bin/env sh
        echo "nvidia-smi $*" >> "$MOCK_COMMAND_LOG"
        if [ "${MOCK_NVIDIA_HOST_FAIL:-0}" = 1 ]; then
          exit 42
        fi
        case "$*" in
          *--query-gpu=memory.total*) printf '%s' "${MOCK_GPU_MEMORY_TOTAL:-6144}" ;;
          *--query-gpu=memory.used*)
            if [ "${MOCK_GPU_QUERY_FAIL:-0}" = 1 ]; then
              echo "mock GPU query failure" >&2
              exit 42
            fi
            printf '%s' "${MOCK_GPU_MEMORY_USED:-0}"
            ;;
          *--query-compute-apps*) printf '%s' "${MOCK_GPU_PROCESSES:-}" ;;
          *) echo "Mock NVIDIA GPU" ;;
        esac
        """,
    )
    _write_executable(
        fake_bin / "sleep",
        """
        #!/usr/bin/env sh
        exit 0
        """,
    )
    _write_executable(
        fake_bin / "curl",
        r"""
        #!/usr/bin/env sh
        echo "curl $*" >> "$MOCK_COMMAND_LOG"
        if [ "${MOCK_CURL_FAIL:-0}" = 1 ]; then
          exit 22
        fi
        printf '{"status":"ready"}'
        """,
    )
    _write_executable(
        fake_bin / "iptables",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import shlex
        import sys
        from pathlib import Path

        args = sys.argv[1:]
        Path(os.environ["MOCK_COMMAND_LOG"]).open("a", encoding="utf-8").write(
            "iptables " + shlex.join(args) + "\n"
        )
        state_path = Path(os.environ["MOCK_IPTABLES_STATE"])
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        elif os.environ["MOCK_DOCKER_USER_CHAIN"] == "1":
            state = {"DOCKER-USER": []}
            if os.environ["MOCK_DOCKER_USER_FORWARD"] == "1":
                state["FORWARD"] = [["-j", "DOCKER-USER"]]
                if os.environ["MOCK_DOCKER_USER_FORWARD_FIRST"] == "0":
                    state["FORWARD"].insert(0, ["-j", "ACCEPT"])
        else:
            state = {}
        action = args[0]
        chain = args[1]
        changed = False
        status = 0
        if action == "-m":
            status = 42 if os.environ["MOCK_CONNTRACK_FAIL"] == "1" else 0
        elif action == "-S":
            status = 0 if chain in state else 1
            if status == 0:
                for rule in state[chain]:
                    print("-A", chain, *rule)
        elif action == "-N":
            if chain in state:
                status = 1
            else:
                state[chain] = []
                changed = True
        elif action == "-F":
            state[chain] = []
            changed = True
        elif action == "-A":
            state.setdefault(chain, []).append(args[2:])
            changed = True
        elif action == "-I":
            index = int(args[2]) - 1
            state.setdefault(chain, []).insert(index, args[3:])
            changed = True
        elif action == "-C":
            status = 0 if args[2:] in state.get(chain, []) else 1
        elif action == "-L":
            for index, rule in enumerate(state.get(chain, []), start=1):
                print(index, *rule)
        else:
            raise SystemExit(f"unsupported mock iptables command: {args}")
        if changed:
            state_path.write_text(json.dumps(state), encoding="utf-8")
        raise SystemExit(status)
        """,
    )
    _write_executable(
        fake_bin / "sudo",
        r"""
        #!/usr/bin/env python3
        import os
        import shlex
        import shutil
        import subprocess
        import sys
        from pathlib import Path

        args = sys.argv[1:]
        Path(os.environ["MOCK_COMMAND_LOG"]).open("a", encoding="utf-8").write(
            "sudo " + shlex.join(args) + "\n"
        )
        root = Path(os.environ["MOCK_HOST_ROOT"])
        if not args or args == ["-v"]:
            raise SystemExit(0)
        command = Path(args[0]).name
        if command == "cat":
            source = root / args[1].lstrip("/")
            if not source.is_file():
                raise SystemExit(1)
            print(source.read_text(encoding="utf-8"), end="")
        elif command == "install":
            if "-d" in args:
                (root / args[-1].lstrip("/")).mkdir(parents=True, exist_ok=True)
            else:
                destination = root / args[-1].lstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args[-2], destination)
                if "-m" in args:
                    destination.chmod(int(args[args.index("-m") + 1], 8))
        elif command == "iptables":
            args[0] = str(Path(__file__).with_name("iptables"))
            raise SystemExit(subprocess.run(args, check=False).returncode)
        elif command == "python3":
            raise SystemExit(subprocess.run(args, check=False).returncode)
        elif command == "firewall-cmd":
            if os.environ["MOCK_FIREWALLD_ADD_FAIL"] == "1" and "--add-rich-rule" in args:
                raise SystemExit(1)
            if any(value.startswith("--get-zone-of-interface=") for value in args):
                print("public")
            elif "--get-default-zone" in args:
                print("public")
            elif "--get-target" in args:
                print("default")
            elif "--list-rich-rules" in args:
                print(os.environ.get("MOCK_BROAD_FIREWALL_RULE", ""))
        elif command == "systemctl" and "restart" in args:
            firewall = root / "usr/local/sbin/chatbot-firewall"
            test_firewall = root / "usr/local/sbin/chatbot-firewall-test"
            test_firewall.write_text(
                firewall.read_text(encoding="utf-8").replace(
                    "IPTABLES='/usr/sbin/iptables'",
                    f"IPTABLES='{Path(__file__).with_name('iptables')}'",
                ),
                encoding="utf-8",
            )
            test_firewall.chmod(0o755)
            for _ in range(2):
                subprocess.run([test_firewall], check=True)
        """,
    )
    for command in ("systemctl", "ufw", "firewall-cmd"):
        _write_executable(
            fake_bin / command,
            f"""
            #!/usr/bin/env sh
            echo "{command} $*" >> "$MOCK_COMMAND_LOG"
            exit 0
            """,
        )
    _write_executable(
        fake_bin / "getenforce",
        """
        #!/usr/bin/env sh
        printf 'Enforcing\n'
        """,
    )
    return fake_bin, command_log, mock_root


def _run_installer(
    tmp_path: Path,
    *,
    chatbot_unhealthy: bool = False,
    chatbot_up_fails: bool = False,
    curl_fails: bool = False,
    docker_ps_fails: bool = False,
    gpu_memory_used: int | str = 0,
    gpu_memory_total: int | str = 6144,
    gpu_processes: str = "",
    gpu_query_fails: bool = False,
    gpu: str = "yes",
    nvidia_runtime: bool = True,
    nvidia_host_fails: bool = False,
    cuda_unavailable: bool = False,
    runtime_images_corrupt: bool = False,
    reset_incomplete: bool = False,
    platform: str = "ubuntu",
    docker_user_chain: bool = True,
    docker_user_forward: bool = True,
    docker_user_forward_first: bool = True,
    conntrack_fails: bool = False,
    bind_address: str = "0.0.0.0",
    http_port: int = 18080,
    firewalld_add_fails: bool = False,
    previous_firewall_state: str = "",
    broad_firewall_rule: str = "",
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    release = _prepare_release(tmp_path)
    if runtime_images_corrupt:
        (release / "images/runtime-images.tar").write_bytes(b"tampered image archive")
    os_release = tmp_path / "os-release"
    if platform in {"ubuntu", "ubuntu-22.04"}:
        ubuntu_version = "22.04" if platform == "ubuntu-22.04" else "26.04"
        os_release.write_text(
            f"ID=ubuntu\nVERSION_ID={ubuntu_version}\n", encoding="utf-8"
        )
    elif platform == "rhel":
        os_release.write_text("ID=rhel\nVERSION_ID=8.10\n", encoding="utf-8")
    else:
        os_release.write_text("ID=unknown\nVERSION_ID=0\n", encoding="utf-8")
    if reset_incomplete:
        shutil.copy2(release / "config/offline.env.template", release / ".env")
    fake_bin, command_log, mock_root = _prepare_fake_commands(tmp_path)
    if previous_firewall_state:
        state_path = mock_root / "etc/chatbot/firewall.conf"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(previous_firewall_state, encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "CLIENT_COUNT": "5",
            "HTTP_PORT": str(http_port),
            "BIND_ADDRESS": bind_address,
            "MOCK_CHATBOT_UNHEALTHY": "1" if chatbot_unhealthy else "0",
            "MOCK_CHATBOT_UP_FAIL": "1" if chatbot_up_fails else "0",
            "MOCK_CHATBOT_PROJECT_NAME": "chatbot-"
            + hashlib.sha256(str(release).encode()).hexdigest()[:12],
            "MOCK_COMMAND_LOG": str(command_log),
            "MOCK_CURL_FAIL": "1" if curl_fails else "0",
            "MOCK_DOCKER_PS_FAIL": "1" if docker_ps_fails else "0",
            "MOCK_DOCKER_USER_CHAIN": "1" if docker_user_chain else "0",
            "MOCK_DOCKER_USER_FORWARD": "1" if docker_user_forward else "0",
            "MOCK_DOCKER_USER_FORWARD_FIRST": "1" if docker_user_forward_first else "0",
            "MOCK_CONNTRACK_FAIL": "1" if conntrack_fails else "0",
            "MOCK_FIREWALLD_ADD_FAIL": "1" if firewalld_add_fails else "0",
            "MOCK_GPU_MEMORY_USED": str(gpu_memory_used),
            "MOCK_GPU_MEMORY_TOTAL": str(gpu_memory_total),
            "MOCK_GPU_PROCESSES": gpu_processes,
            "MOCK_GPU_QUERY_FAIL": "1" if gpu_query_fails else "0",
            "MOCK_NVIDIA_RUNTIME": "1" if nvidia_runtime else "0",
            "MOCK_BROAD_FIREWALL_RULE": broad_firewall_rule,
            "MOCK_NVIDIA_HOST_FAIL": "1" if nvidia_host_fails else "0",
            "MOCK_CUDA_UNAVAILABLE": "1" if cuda_unavailable else "0",
            "MOCK_HOST_ROOT": str(mock_root),
            "MOCK_IPTABLES_STATE": str(tmp_path / "iptables-state.json"),
            "HOST_OS_RELEASE": str(os_release),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "RESET_INCOMPLETE_INSTALL": "YES" if reset_incomplete else "",
        }
    )
    environment.pop("OFFLINE_ENV", None)
    result = subprocess.run(
        ["bash", "./setup.sh", "--gpu", gpu],
        cwd=release,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, release, command_log, mock_root


def test_installer_completes_with_five_clients_and_host_automation(
    tmp_path: Path,
) -> None:
    result, release, command_log, mock_root = _run_installer(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    environment_text = (release / ".env").read_text(encoding="utf-8")
    assert "SERVER_ADDRESS=192.168.50.10" in environment_text
    assert "HTTP_PORT=18080" in environment_text
    assert "LLAMA_GPU_LAYERS=16" in environment_text
    assert "EMBEDDING_CTX_SIZE=2048" in environment_text
    assert "EMBEDDING_BATCH_SIZE=2048" in environment_text
    assert "EMBEDDING_UBATCH_SIZE=2048" in environment_text
    assert "APP_IMAGE=chatbot:0.2.3" in environment_text

    auth = json.loads(
        (release / "config/auth/api_keys.json").read_text(encoding="utf-8")
    )
    assert [client["id"] for client in auth["clients"]] == [
        f"client-{number:02d}" for number in range(1, 6)
    ]
    assert len({client["token_sha256"] for client in auth["clients"]}) == 5
    credentials = sorted((release / "config/clients").glob("client-*.txt"))
    assert len(credentials) == 5
    assert all(
        "Chatbot URL: http://192.168.50.10:18080" in path.read_text()
        for path in credentials
    )

    commands = command_log.read_text(encoding="utf-8")
    removal_line = next(
        line for line in commands.splitlines() if line.startswith("docker rm -f ")
    )
    assert removal_line == EXPECTED_REMOVAL_COMMAND
    for unrelated_name in (
        "chatbot",
        "chatbot-postgres",
        "llama-server",
        "embedding-server",
        "chatbot-chromadb",
        "camofox-browser",
        "unrelated-project-worker",
        "Chatbot-uppercase",
    ):
        assert unrelated_name not in removal_line
    volume_removal_line = next(
        line for line in commands.splitlines() if line.startswith("docker volume rm ")
    )
    assert volume_removal_line == EXPECTED_VOLUME_REMOVAL_COMMAND
    assert "generic-project-volume" not in volume_removal_line
    assert "unrelated-volume" not in volume_removal_line
    assert commands.count("docker load -i ") == 1
    assert any(
        line == "sudo /usr/sbin/iptables -m conntrack -h"
        for line in commands.splitlines()
    )
    assert f"--project-directory {release}" in commands
    assert "compose/docker-compose.offline.gpu.yml" in commands
    assert "docker update --restart=no" not in commands
    assert "ufw allow from 192.168.50.0/24 to any port 18080" in commands
    assert "systemctl enable docker.service" in commands

    firewall_program = (mock_root / "usr/local/sbin/chatbot-firewall").read_text(
        encoding="utf-8"
    )
    assert "HTTP_PORT='18080'" in firewall_program
    assert "IPTABLES='/usr/sbin/iptables'" in firewall_program
    assert "PROXY_CONTAINER_PORT='80'" in firewall_program
    subprocess.run(
        ["bash", "-n", str(mock_root / "usr/local/sbin/chatbot-firewall")], check=True
    )
    assert '--ctorigdstport "$HTTP_PORT" -j DROP' in firewall_program

    firewall_state = json.loads(
        (tmp_path / "iptables-state.json").read_text(encoding="utf-8")
    )
    assert firewall_state["DOCKER-USER"] == [["-j", "CHATBOT"]]
    assert firewall_state["CHATBOT"] == [
        [
            "-s",
            "192.168.50.0/24",
            "-p",
            "tcp",
            "--dport",
            "80",
            "-m",
            "conntrack",
            "--ctdir",
            "ORIGINAL",
            "--ctorigdstport",
            "18080",
            "-j",
            "ACCEPT",
        ],
        [
            "-p",
            "tcp",
            "--dport",
            "80",
            "-m",
            "conntrack",
            "--ctdir",
            "ORIGINAL",
            "--ctorigdstport",
            "18080",
            "-j",
            "DROP",
        ],
        ["-j", "RETURN"],
    ]
    assert (release / "config/.installed").is_file()
    install_log = (release / "install.log").read_text(encoding="utf-8")
    assert "STEP 15/15" in install_log
    assert "Generated 5 unique client credential file(s)" in install_log


def test_installer_accepts_ubuntu_2204(tmp_path: Path) -> None:
    result, _, command_log, _ = _run_installer(tmp_path, platform="ubuntu-22.04")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Supported target platform: ubuntu" in result.stdout
    assert "docker rm -f" in command_log.read_text(encoding="utf-8")


def test_installer_rejects_unavailable_conntrack_before_cleanup(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, conntrack_fails=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "Docker firewall conntrack matching is unavailable." in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "iptables -m conntrack -h" in commands
    assert "docker rm -f" not in commands


def test_installer_rejects_missing_docker_user_before_cleanup(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, docker_user_chain=False)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "required DOCKER-USER firewall chain" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "iptables -S DOCKER-USER" in commands
    assert "docker rm -f" not in commands


def test_installer_rejects_detached_docker_user_before_cleanup(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path, docker_user_forward=False
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "does not route forwarded traffic" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "iptables -S FORWARD" in commands
    assert "docker rm -f" not in commands


def test_installer_rejects_nonleading_docker_user_before_cleanup(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path, docker_user_forward_first=False
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "before other FORWARD rules" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "iptables -S FORWARD" in commands
    assert "docker rm -f" not in commands


def test_installer_preserves_incomplete_state_when_docker_user_is_missing(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path, docker_user_chain=False, reset_incomplete=True
    )

    assert result.returncode != 0
    assert (release / ".env").exists()
    assert "required DOCKER-USER firewall chain" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker compose --project-directory" not in commands
    assert "docker rm -f" not in commands


@pytest.mark.parametrize("platform", ["ubuntu", "rhel"])
def test_installer_uses_cpu_without_nvidia_support(
    tmp_path: Path, platform: str
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path,
        gpu="no",
        nvidia_runtime=False,
        nvidia_host_fails=True,
        platform=platform,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    environment_text = (release / ".env").read_text(encoding="utf-8")
    assert "ACCELERATOR=cpu" in environment_text
    assert "LLAMA_GPU_LAYERS=0" in environment_text
    assert "LLAMA_GPU_LAYERS_DRAFT=0" in environment_text
    assert "EMBEDDING_GPU_LAYERS=0" in environment_text
    commands = command_log.read_text(encoding="utf-8")
    assert "nvidia-smi" not in commands
    assert "--gpus all" not in commands
    assert f"--project-directory {release}" in commands
    assert "docker compose --project-directory" in commands
    assert "compose/docker-compose.offline.gpu.yml" not in commands


def test_installer_configures_rhel_firewalld_without_ufw(tmp_path: Path) -> None:
    result, release, command_log, mock_root = _run_installer(
        tmp_path,
        gpu="no",
        platform="rhel",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "firewall-cmd --state" in commands
    assert "--add-rich-rule" in commands
    assert "--remove-service=ssh" in commands
    assert commands.index("--add-rich-rule") < commands.index("--remove-service=ssh")
    assert commands.index("iptables -m conntrack -h") < commands.index("docker rm -f")
    assert commands.index("firewall-cmd --state") < commands.index("docker rm -f")
    assert "--reload" not in commands
    assert "ufw " not in commands
    firewall_state = (mock_root / "etc/chatbot/firewall.conf").read_text(
        encoding="utf-8"
    )
    assert "FIREWALL_BACKEND=firewalld" in firewall_state
    assert "FIREWALL_ZONE=public" in firewall_state


def test_firewalld_add_failure_preserves_broad_access(tmp_path: Path) -> None:
    result, _, command_log, _ = _run_installer(
        tmp_path,
        gpu="no",
        platform="rhel",
        firewalld_add_fails=True,
    )

    assert result.returncode != 0
    commands = command_log.read_text(encoding="utf-8")
    assert "--add-rich-rule" in commands
    assert "--remove-service=ssh" not in commands
    assert "--remove-port=22/tcp" not in commands


def test_firewalld_keeps_unchanged_previous_rules(tmp_path: Path) -> None:
    previous_state = "\n".join(
        (
            "FIREWALL_BACKEND=firewalld",
            "FIREWALL_ZONE=public",
            "LAN_CIDR=192.168.50.0/24",
            "SERVER_ADDRESS=192.168.50.10",
            "HTTP_PORT=18080",
            "SSH_PORT=22",
            "",
        )
    )
    result, _, command_log, _ = _run_installer(
        tmp_path,
        gpu="no",
        platform="rhel",
        previous_firewall_state=previous_state,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Keeping unchanged installer-owned firewalld rules" in result.stdout
    assert "--remove-rich-rule" not in command_log.read_text(encoding="utf-8")


def test_installer_rejects_broad_rhel_firewalld_rule_before_cleanup(
    tmp_path: Path,
) -> None:
    result, _, command_log, _ = _run_installer(
        tmp_path,
        gpu="no",
        platform="rhel",
        broad_firewall_rule='rule family="ipv4" port port="22" protocol="tcp" accept',
    )

    assert result.returncode != 0
    assert "broad accepting rule for TCP port 22" in result.stdout
    assert "docker rm -f" not in command_log.read_text(encoding="utf-8")


def test_installer_rejects_tampered_runtime_image_archive_before_load(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path, gpu="no", runtime_images_corrupt=True
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "runtime image archive checksum does not match" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker load -i" not in commands
    assert "docker rm -f" not in commands


def test_installer_rejects_under_capacity_gpu_before_cleanup(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, gpu_memory_total=6143)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "requires at least 6144 MiB" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "--query-gpu=memory.total" in commands
    assert "docker rm -f" not in commands


def test_installer_rejects_gpu_without_nvidia_runtime_before_cleanup(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path, gpu="yes", nvidia_runtime=False
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "Docker NVIDIA runtime" in result.stdout
    assert "docker rm -f" not in command_log.read_text(encoding="utf-8")


def test_installer_rejects_unknown_accelerator_before_cleanup(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, gpu="tpu")

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "--gpu must be yes or no" in result.stdout
    commands = command_log.read_text(encoding="utf-8") if command_log.is_file() else ""
    assert "docker rm -f" not in commands


def test_installer_rolls_back_generated_state_after_readiness_failure(
    tmp_path: Path,
) -> None:
    result, release, command_log, mock_root = _run_installer(tmp_path, curl_fails=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert not (release / "config/.installed").exists()
    assert not (release / "config/auth").exists()
    assert not (release / "config/clients").exists()
    assert (mock_root / "etc/chatbot/firewall.conf").is_file()
    commands = command_log.read_text(encoding="utf-8")
    assert EXPECTED_REMOVAL_COMMAND in commands
    assert EXPECTED_VOLUME_REMOVAL_COMMAND in commands
    assert "down -v --remove-orphans" in commands
    assert (
        "Removed selected chatbot containers and volumes are not restored"
        in result.stdout
    )


def test_installer_prints_chatbot_logs_before_startup_rollback(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, chatbot_up_fails=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert (
        "Service startup failed; printing status and diagnostic logs" in result.stdout
    )
    assert "mock chatbot database authentication failure" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker compose" in commands and "logs --tail=200 postgres" in commands
    assert "chatbot proxy" in commands
    assert "down -v --remove-orphans" in commands


def test_installer_prints_diagnostics_when_chatbot_remains_unhealthy(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, chatbot_unhealthy=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "Service did not become ready: chatbot" in result.stdout
    assert "mock chatbot database authentication failure" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker compose" in commands and "logs --tail=200 postgres" in commands
    assert "chatbot proxy" in commands
    assert "down -v --remove-orphans" in commands


def test_reset_removes_previous_project_and_legacy_volumes(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(tmp_path, reset_incomplete=True)

    assert result.returncode == 0, result.stdout + result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "down -v --remove-orphans" in commands
    assert EXPECTED_VOLUME_REMOVAL_COMMAND in commands


def test_installer_allows_small_desktop_gpu_usage(tmp_path: Path) -> None:
    desktop_processes = (
        "6843, /usr/bin/nautilus, 37\n"
        "1852516, /usr/bin/ptyxis, 21\n"
        "1937544, /usr/bin/gnome-text-editor, 11"
    )
    result, _, _, _ = _run_installer(
        tmp_path, gpu_memory_used=69, gpu_processes=desktop_processes
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Total residual GPU memory: 69 MiB" in result.stdout
    assert "total residual GPU usage is below 1024 MiB" in result.stdout


def test_installer_allows_1023_mib_residual_gpu_usage(tmp_path: Path) -> None:
    result, _, _, _ = _run_installer(
        tmp_path,
        gpu_memory_used=1023,
        gpu_processes="42, /usr/bin/desktop-process, 1023",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Total residual GPU memory: 1023 MiB" in result.stdout
    assert "total residual GPU usage is below 1024 MiB" in result.stdout


def test_incomplete_gpu_reset_stops_labeled_containers_before_gpu_check(
    tmp_path: Path,
) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path,
        reset_incomplete=True,
        gpu_memory_used=1024,
    )

    assert result.returncode != 0
    assert (release / ".env").exists()
    commands = command_log.read_text(encoding="utf-8")
    assert commands.index("docker stop current-labeled") < commands.index(
        "nvidia-smi --query-gpu=memory.used"
    )
    assert "docker rm -f" not in commands
    assert "docker volume rm" not in commands


def test_installer_blocks_1024_mib_residual_gpu_usage(tmp_path: Path) -> None:
    result, release, command_log, mock_root = _run_installer(
        tmp_path,
        gpu_memory_used=1024,
        gpu_processes="42, /app/llama-server, 1024",
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert not (mock_root / "etc/chatbot/firewall.conf").exists()
    assert "Total residual GPU memory: 1024 MiB" in result.stdout
    assert "Residual GPU usage is at least 1024 MiB" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker rm -f" not in commands
    assert "docker volume rm" not in commands


def test_installer_rejects_occupied_http_port_before_cleanup(tmp_path: Path) -> None:
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        http_port = listener.getsockname()[1]
        result, release, command_log, _ = _run_installer(
            tmp_path,
            gpu="no",
            http_port=http_port,
        )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "bind address is unavailable or port is in use" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert f"sudo python3 - 0.0.0.0 192.168.50.10 {http_port} 22" in commands
    assert "docker rm -f" not in commands
    assert "docker volume rm" not in commands


def test_installer_rejects_invalid_bind_address_before_cleanup(tmp_path: Path) -> None:
    result, release, command_log, _ = _run_installer(
        tmp_path,
        bind_address="not-an-ip-address",
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "invalid IPv4 bind address" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "docker rm -f" not in commands
    assert "docker volume rm" not in commands


def test_installer_rejects_invalid_gpu_memory_measurement(tmp_path: Path) -> None:
    result, release, _, mock_root = _run_installer(tmp_path, gpu_memory_used="N/A")

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert not (mock_root / "etc/chatbot/firewall.conf").exists()
    assert "invalid total GPU memory measurement" in result.stdout
    assert "N/A" in result.stdout


def test_installer_fails_closed_when_gpu_query_fails(tmp_path: Path) -> None:
    result, release, _, mock_root = _run_installer(tmp_path, gpu_query_fails=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert not (mock_root / "etc/chatbot/firewall.conf").exists()
    assert "Could not measure total NVIDIA GPU memory use" in result.stdout
    assert "mock GPU query failure" in result.stdout


def test_installer_aborts_if_docker_inventory_fails(tmp_path: Path) -> None:
    result, release, command_log, mock_root = _run_installer(
        tmp_path, docker_ps_fails=True
    )

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert not (mock_root / "etc/chatbot/firewall.conf").exists()
    commands = command_log.read_text(encoding="utf-8")
    assert "docker ps -aq" in commands
    assert "docker rm -f" not in commands
    assert "docker update --restart=no" not in commands


def test_installer_rejects_gpu_when_cuda_container_is_unavailable(
    tmp_path: Path,
) -> None:
    result, release, _, _ = _run_installer(tmp_path, gpu="yes", cuda_unavailable=True)

    assert result.returncode != 0
    assert not (release / ".env").exists()
    assert "CUDA container validation failed" in result.stdout


def test_installer_online_mode_delegates_to_accelerator(tmp_path: Path) -> None:
    release = _prepare_release(tmp_path)
    for relative_path in (
        "compose/docker-compose.yml",
        "compose/docker-compose.gpu.yml",
        ".env.example",
    ):
        destination = release / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative_path, destination)
    # Replace accelerator.sh with a stub that records the delegated invocation and
    # is a no-op when sourced (so setup.sh's `source` defines nothing for --gpu no).
    _write_executable(
        release / "scripts/accelerator.sh",
        r"""
        #!/usr/bin/env bash
        if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
          printf 'accelerator.sh %s\n' "$*" >> "$MOCK_COMMAND_LOG"
          exit 0
        fi
        """,
    )
    fake_bin, command_log, _ = _prepare_fake_commands(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "MOCK_COMMAND_LOG": str(command_log),
            "PATH": f"{fake_bin}:{environment['PATH']}",
        }
    )
    environment.pop("OFFLINE_ENV", None)
    result = subprocess.run(
        ["bash", "./setup.sh", "--mode", "online", "--gpu", "no"],
        cwd=release,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STEP 4/4" in result.stdout
    assert (release / ".env").is_file()
    assert (release / ".env").read_text(encoding="utf-8") == (
        release / ".env.example"
    ).read_text(encoding="utf-8")
    commands = command_log.read_text(encoding="utf-8")
    assert "accelerator.sh online cpu start" in commands
    # Online mode performs no offline hardening.
    assert not (release / "config/.installed").exists()
    assert not (release / "config/clients").exists()
    assert "configure_host.sh" not in commands
    assert "manage_client.sh" not in commands
