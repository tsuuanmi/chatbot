"""Optional NVIDIA runtime acceptance."""

from __future__ import annotations

import sys

from .proc import run

def gpu_runtime_check() -> None:
    run(
        sys.executable,
        "-m",
        "tools.check_gpu_runtime",
    )
