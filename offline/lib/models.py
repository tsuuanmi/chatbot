"""Install and verify an offline model bundle."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def read_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(
            f"required file is missing: {path}"
        )

    values: dict[str, str] = {}

    for raw in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw.strip()

        if not line:
            continue

        if "=" not in line:
            raise RuntimeError(
                f"invalid line in {path}: {raw!r}"
            )

        key, value = line.split("=", 1)
        values[key] = value

    return values


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)

            if not block:
                break

            hasher.update(block)

    return hasher.hexdigest()


def digest_stream(handle) -> str:
    hasher = hashlib.sha256()

    while True:
        block = handle.read(1024 * 1024)

        if not block:
            break

        hasher.update(block)

    return hasher.hexdigest()


def parse_checksums(
    content: str,
) -> dict[str, str]:
    result: dict[str, str] = {}

    for raw in content.splitlines():
        if not raw.strip():
            continue

        expected, separator, relative = (
            raw.partition("  ")
        )

        if (
            not separator
            or not expected
            or not relative
            or relative in result
        ):
            raise RuntimeError(
                f"invalid checksum entry: {raw!r}"
            )

        path = PurePosixPath(relative)

        if (
            path.is_absolute()
            or ".." in path.parts
        ):
            raise RuntimeError(
                f"unsafe checksum path: {relative}"
            )

        result[relative] = expected

    return result


def runtime_expectation(
    root: Path,
) -> dict[str, str]:
    manifest = read_values(
        root / "BUNDLE-MANIFEST.txt"
    )

    required = {
        "model_bundle_version": manifest.get(
            "required_model_bundle",
            "",
        ),
        "llama_model": manifest.get(
            "llama_model",
            "",
        ),
        "mmproj_model": manifest.get(
            "mmproj_model",
            "",
        ),
        "mtp_model": manifest.get(
            "mtp_model",
            "",
        ),
        "llama_spec_type": manifest.get(
            "llama_spec_type",
            "",
        ),
        "llama_spec_draft_n_max": manifest.get(
            "llama_spec_draft_n_max",
            "",
        ),
    }

    missing = [
        key
        for key, value in required.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "runtime manifest is missing model "
            "requirements: "
            + ", ".join(missing)
        )

    return required


def validate_manifest(
    manifest: dict[str, str],
    expected: dict[str, str],
) -> None:
    for key, value in expected.items():
        actual = manifest.get(key, "")

        if actual != value:
            raise RuntimeError(
                "model bundle mismatch: "
                f"{key} expected={value!r} "
                f"actual={actual!r}"
            )

    for key in (
        "llama_model_sha256",
        "mmproj_model_sha256",
        "mtp_model_sha256",
    ):
        if not manifest.get(key):
            raise RuntimeError(
                f"model manifest missing: {key}"
            )


def verify_installed(
    root: Path,
    expected: dict[str, str],
) -> Path:
    manifest_path = (
        root / "MODELS-MANIFEST.txt"
    )

    checksum_path = (
        root / "SHA256SUMS"
    )

    manifest = read_values(
        manifest_path
    )

    validate_manifest(
        manifest,
        expected,
    )

    checksums = parse_checksums(
        checksum_path.read_text(
            encoding="utf-8"
        )
    )

    for relative, expected_digest in (
        checksums.items()
    ):
        path = root / relative

        if not path.is_file():
            raise RuntimeError(
                "installed model bundle file "
                f"is missing: {relative}"
            )

        actual = digest_file(path)

        if actual != expected_digest:
            raise RuntimeError(
                "installed model checksum "
                f"mismatch: {relative}"
            )

    for name_key, digest_key in (
        (
            "llama_model",
            "llama_model_sha256",
        ),
        (
            "mmproj_model",
            "mmproj_model_sha256",
        ),
        (
            "mtp_model",
            "mtp_model_sha256",
        ),
    ):
        name = manifest[name_key]

        if Path(name).name != name:
            raise RuntimeError(
                f"invalid model filename: {name}"
            )

        relative = f"models/{name}"

        if (
            checksums.get(relative)
            != manifest[digest_key]
        ):
            raise RuntimeError(
                f"model digest mismatch: {name}"
            )

    model_dir = root / "models"

    if not model_dir.is_dir():
        raise RuntimeError(
            "installed model directory is missing"
        )

    return model_dir


def verify_archive(
    archive: Path,
    expected: dict[str, str],
) -> str:
    expected_root = (
        "chatbot-models-"
        + expected["model_bundle_version"]
    )

    if archive.name != (
        expected_root + ".zip"
    ):
        raise RuntimeError(
            "unexpected model package filename: "
            f"{archive.name}"
        )

    with zipfile.ZipFile(
        archive,
        mode="r",
    ) as source:
        files = {
            info.filename
            for info in source.infolist()
            if not info.is_dir()
        }

        for name in files:
            path = PurePosixPath(name)

            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0]
                != expected_root
            ):
                raise RuntimeError(
                    f"unsafe ZIP member: {name}"
                )

        manifest_member = (
            f"{expected_root}/"
            "MODELS-MANIFEST.txt"
        )

        checksum_member = (
            f"{expected_root}/"
            "SHA256SUMS"
        )

        for required in (
            manifest_member,
            checksum_member,
        ):
            if required not in files:
                raise RuntimeError(
                    "model package file is "
                    f"missing: {required}"
                )

        manifest_text = source.read(
            manifest_member
        ).decode("utf-8")

        manifest: dict[str, str] = {}

        for raw in (
            manifest_text.splitlines()
        ):
            if not raw.strip():
                continue

            if "=" not in raw:
                raise RuntimeError(
                    "invalid model manifest line"
                )

            key, value = raw.split(
                "=",
                1,
            )

            manifest[key] = value

        validate_manifest(
            manifest,
            expected,
        )

        checksums = parse_checksums(
            source.read(
                checksum_member
            ).decode("utf-8")
        )

        expected_files = {
            checksum_member,
        }

        expected_files.update(
            f"{expected_root}/{relative}"
            for relative in checksums
        )

        if files != expected_files:
            extra = sorted(
                files - expected_files
            )

            missing = sorted(
                expected_files - files
            )

            raise RuntimeError(
                "model ZIP contents differ from "
                f"checksums; extra={extra} "
                f"missing={missing}"
            )

        actual_digests: dict[str, str] = {}

        for relative, expected_digest in (
            checksums.items()
        ):
            member = (
                f"{expected_root}/{relative}"
            )

            with source.open(
                member,
                mode="r",
            ) as handle:
                actual = digest_stream(
                    handle
                )

            if actual != expected_digest:
                raise RuntimeError(
                    "model package checksum "
                    f"mismatch: {relative}"
                )

            actual_digests[
                relative
            ] = actual

        for name_key, digest_key in (
            (
                "llama_model",
                "llama_model_sha256",
            ),
            (
                "mmproj_model",
                "mmproj_model_sha256",
            ),
            (
                "mtp_model",
                "mtp_model_sha256",
            ),
        ):
            name = manifest[name_key]

            relative = f"models/{name}"

            if (
                actual_digests.get(relative)
                != manifest[digest_key]
            ):
                raise RuntimeError(
                    f"manifest digest mismatch: {name}"
                )

    return expected_root


def locate_package(
    root: Path,
    version: str,
    requested: str,
) -> Path:
    expected_name = (
        f"chatbot-models-{version}.zip"
    )

    if requested:
        path = Path(requested).expanduser()

        if not path.is_absolute():
            path = (
                Path.cwd() / path
            )

        return path.resolve()

    candidates = (
        root / expected_name,
        root.parent / expected_name,
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise RuntimeError(
        "required model package is unavailable; "
        f"expected {expected_name} beside the "
        "runtime directory or specify MODEL_PACKAGE"
    )


def install(
    root: Path,
    store: Path,
    package: str,
) -> Path:
    expected = runtime_expectation(
        root
    )

    version = expected[
        "model_bundle_version"
    ]

    store = (
        store.expanduser().resolve()
    )

    store.mkdir(
        parents=True,
        exist_ok=True,
    )

    installed = (
        store / version
    )

    if installed.exists():
        model_dir = verify_installed(
            installed,
            expected,
        )

        print(
            "MODEL PACKAGE REUSE PASS"
        )
        print(
            f"MODEL_DIR={model_dir}"
        )

        return model_dir

    archive = locate_package(
        root,
        version,
        package,
    )

    if not archive.is_file():
        raise RuntimeError(
            f"model package not found: {archive}"
        )

    expected_root = verify_archive(
        archive,
        expected,
    )

    with tempfile.TemporaryDirectory(
        prefix=".chatbot-model-install-",
        dir=store,
    ) as temporary:
        temporary_path = Path(
            temporary
        )

        with zipfile.ZipFile(
            archive,
            mode="r",
        ) as source:
            source.extractall(
                temporary_path
            )

        extracted = (
            temporary_path
            / expected_root
        )

        verify_installed(
            extracted,
            expected,
        )

        if installed.exists():
            raise RuntimeError(
                "model destination appeared "
                "during installation"
            )

        os.replace(
            extracted,
            installed,
        )

    model_dir = verify_installed(
        installed,
        expected,
    )

    print(
        "MODEL PACKAGE INSTALL PASS"
    )
    print(
        f"MODEL_PACKAGE={archive}"
    )
    print(
        f"MODEL_DIR={model_dir}"
    )

    return model_dir


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "command",
        choices=("install",),
    )

    parser.add_argument(
        "--root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--store",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--package",
        default="",
    )

    args = parser.parse_args()

    try:
        install(
            args.root.resolve(),
            args.store,
            args.package,
        )
    except Exception as exc:
        raise SystemExit(
            f"ERROR: {exc}"
        ) from exc


if __name__ == "__main__":
    main()
