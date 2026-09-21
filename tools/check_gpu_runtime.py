"""Verify that the running llama-server is actually using GPU mode."""

from __future__ import annotations

import json
import subprocess


def run(*args: str) -> str:
    return subprocess.check_output(
        args,
        text=True,
    ).strip()


def main() -> None:
    cid = run(
        "docker",
        "compose",
        "--env-file",
        ".env",
        "--env-file",
        "versions.env",
        "-f",
        "compose.yaml",
        "-f",
        "compose.gpu.yaml",
        "ps",
        "-q",
        "llama-server",
    )

    if not cid:
        raise RuntimeError(
            "llama-server is not running"
        )

    requests_raw = run(
        "docker",
        "inspect",
        cid,
        "--format",
        "{{json .HostConfig.DeviceRequests}}",
    )

    requests = json.loads(
        requests_raw
    )

    if not requests:
        raise RuntimeError(
            "llama-server has no GPU device request"
        )

    image_id = run(
        "docker",
        "inspect",
        cid,
        "--format",
        "{{.Image}}",
    )

    expected_image_id = run(
        "docker",
        "image",
        "inspect",
        "--format",
        "{{.Id}}",
        run(
            "bash",
            "-c",
            "set -a; source versions.env; "
            'printf "%s" "$LLAMA_GPU_IMAGE"',
        ),
    )

    if image_id != expected_image_id:
        raise RuntimeError(
            "llama-server is not using LLAMA_GPU_IMAGE"
        )

    devices = run(
        "docker",
        "exec",
        cid,
        "/app/llama-server",
        "--list-devices",
    )

    if "CUDA0:" not in devices:
        raise RuntimeError(
            "CUDA device is not visible to llama-server"
        )

    print(devices)
    print()
    print("GPU RUNTIME ACCEPTANCE PASS")


if __name__ == "__main__":
    main()
