from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path


MODELS = {
    "gemma-4-E2B-it-Q4_K_M.gguf": (
        "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/"
        "resolve/0314792d7f1f7e229411f620751375812bb9faf2/"
        "gemma-4-E2B-it-Q4_K_M.gguf"
    ),
    "mmproj-gemma-4-E2B-it-bf16.gguf": (
        "https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/"
        "resolve/b4243c156154b6dca9324415f8c7ccc098b4aed1/"
        "mmproj-gemma-4-E2B-it-BF16.gguf"
    ),
    "mtp-gemma-4-E2B-it.gguf": (
        "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/"
        "resolve/0314792d7f1f7e229411f620751375812bb9faf2/"
        "mtp-gemma-4-E2B-it.gguf"
    ),

    # Gemma 4 E2B official QAT Q4_0 candidate.
    "gemma-4-E2B_q4_0-it.gguf": (
        "https://huggingface.co/google/"
        "gemma-4-E2B-it-qat-q4_0-gguf/"
        "resolve/675cff42a74c774d6cb76f76d8eacb49b48c9b93/"
        "gemma-4-E2B_q4_0-it.gguf"
    ),
    "gemma-4-E2B-it-mmproj.gguf": (
        "https://huggingface.co/google/"
        "gemma-4-E2B-it-qat-q4_0-gguf/"
        "resolve/675cff42a74c774d6cb76f76d8eacb49b48c9b93/"
        "gemma-4-E2B-it-mmproj.gguf"
    ),

    # QAT-specific MTP drafter.
    #
    # The upstream filename is also mtp-gemma-4-E2B-it.gguf,
    # so keep a distinct local name to avoid overwriting the
    # non-QAT baseline drafter.
    "mtp-gemma-4-E2B-it-qat.gguf": (
        "https://huggingface.co/unsloth/"
        "gemma-4-E2B-it-qat-GGUF/"
        "resolve/66a399f68ddd113b06dff02fca9523e55465d11d/"
        "mtp-gemma-4-E2B-it.gguf"
    ),

}


def load_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing environment file: {path}")

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        os.environ.setdefault(key, value)


def download(url: str, destination: Path) -> None:
    part = destination.with_name(destination.name + ".part")

    print(f"Downloading {destination.name}")
    print(f"  -> {destination}")

    try:
        with urllib.request.urlopen(url) as response, part.open("wb") as output:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header else None

            downloaded = 0
            last_percent = -1

            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break

                output.write(chunk)
                downloaded += len(chunk)

                if total:
                    percent = int(downloaded * 100 / total)
                    if percent != last_percent:
                        print(
                            f"\r  {percent:3d}% "
                            f"({downloaded / 1024**3:.2f}/"
                            f"{total / 1024**3:.2f} GiB)",
                            end="",
                            flush=True,
                        )
                        last_percent = percent

            if total:
                print()

        part.replace(destination)

    except Exception:
        part.unlink(missing_ok=True)
        raise


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env"

    load_env(env_path)

    model_dir_raw = os.environ.get("MODEL_DIR", "./runtime/models")
    model_dir = Path(model_dir_raw)

    if not model_dir.is_absolute():
        model_dir = repo_root / model_dir

    model_dir.mkdir(parents=True, exist_ok=True)

    required = {
        os.environ.get(
            "LLAMA_MODEL_NAME",
            "gemma-4-E2B-it-Q4_K_M.gguf",
        ),
        os.environ.get(
            "MMPROJ_MODEL",
            "mmproj-gemma-4-E2B-it-bf16.gguf",
        ),
        os.environ.get(
            "MTP_MODEL_NAME",
            "mtp-gemma-4-E2B-it.gguf",
        ),
    }

    unknown = required - MODELS.keys()

    if unknown:
        print(
            "No pinned download URL is configured for:",
            file=sys.stderr,
        )
        for name in sorted(unknown):
            print(f"  - {name}", file=sys.stderr)
        return 1

    print(f"Model directory: {model_dir}")

    downloaded = 0
    skipped = 0

    for name in sorted(required):
        destination = model_dir / name

        if destination.is_file() and destination.stat().st_size > 0:
            print(f"Model already exists: {name}")
            skipped += 1
            continue

        download(MODELS[name], destination)
        downloaded += 1

    print()
    print(
        f"MODELS PASS "
        f"(downloaded={downloaded}, existing={skipped})"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
