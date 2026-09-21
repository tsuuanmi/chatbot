"""Independent offline model package builder and verifier."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .env import (
    read_env,
    require,
)
from .manifest import (
    digest,
    write_checksums,
    write_manifest,
)


_VERSION_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
)


def _validate_version(
    version: str,
) -> str:
    if not _VERSION_RE.fullmatch(version):
        raise RuntimeError(
            f"invalid model bundle version: {version!r}"
        )

    return version


def _stream_digest(
    handle,
) -> str:
    hasher = hashlib.sha256()

    while True:
        block = handle.read(
            1024 * 1024
        )

        if not block:
            break

        hasher.update(block)

    return hasher.hexdigest()


def _parse_values(
    content: str,
    label: str,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw in content.splitlines():
        line = raw.strip()

        if not line:
            continue

        if "=" not in line:
            raise RuntimeError(
                f"invalid {label} line: {raw!r}"
            )

        key, value = line.split(
            "=",
            1,
        )

        values[key] = value

    return values


def _parse_checksums(
    content: str,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw in content.splitlines():
        if not raw.strip():
            continue

        expected, separator, relative = (
            raw.partition("  ")
        )

        if not separator:
            raise RuntimeError(
                f"invalid checksum line: {raw!r}"
            )

        if (
            not expected
            or not relative
            or relative in values
        ):
            raise RuntimeError(
                f"invalid checksum entry: {raw!r}"
            )

        values[relative] = expected

    return values


def build(
    version: str | None = None,
    dist: Path = Path("dist"),
) -> Path:
    runtime = read_env(
        Path(".env.example")
    )

    local = read_env(
        Path(".env")
    )

    require(
        runtime,
        "MODEL_BUNDLE_VERSION",
        "LLAMA_MODEL_NAME",
        "MMPROJ_MODEL",
        "MTP_MODEL_NAME",
        "LLAMA_SPEC_TYPE",
        "LLAMA_SPEC_DRAFT_N_MAX",
    )

    require(
        local,
        "MODEL_DIR",
    )

    version = _validate_version(
        version
        or os.environ.get("MODEL_VERSION", "")
        or runtime["MODEL_BUNDLE_VERSION"]
    )

    model_dir = Path(
        local["MODEL_DIR"]
    )

    llama_name = runtime[
        "LLAMA_MODEL_NAME"
    ]

    mmproj_name = runtime[
        "MMPROJ_MODEL"
    ]

    mtp_name = runtime[
        "MTP_MODEL_NAME"
    ]

    llama_source = (
        model_dir
        / llama_name
    )

    mmproj_source = (
        model_dir
        / mmproj_name
    )

    mtp_source = (
        model_dir
        / mtp_name
    )

    for label, path in (
        ("llama model", llama_source),
        ("multimodal projector", mmproj_source),
        ("MTP model", mtp_source),
    ):
        if not path.is_file():
            raise RuntimeError(
                f"{label} not found: {path}"
            )

    dist.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = (
        dist
        / f"chatbot-models-{version}.zip"
    )

    if archive.exists():
        raise RuntimeError(
            f"model package already exists: {archive}"
        )

    with tempfile.TemporaryDirectory(
        prefix=".chatbot-models-",
        dir=dist,
    ) as temporary:
        root = (
            Path(temporary)
            / f"chatbot-models-{version}"
        )

        models = (
            root
            / "models"
        )

        models.mkdir(
            parents=True
        )

        llama_target = (
            models
            / llama_name
        )

        mmproj_target = (
            models
            / mmproj_name
        )

        mtp_target = (
            models
            / mtp_name
        )

        shutil.copy2(
            llama_source,
            llama_target,
        )

        shutil.copy2(
            mmproj_source,
            mmproj_target,
        )

        shutil.copy2(
            mtp_source,
            mtp_target,
        )

        llama_sha256 = digest(
            llama_target
        )

        mmproj_sha256 = digest(
            mmproj_target
        )

        mtp_sha256 = digest(
            mtp_target
        )

        write_manifest(
            root / "MODELS-MANIFEST.txt",
            {
                "model_bundle_version": version,
                "llama_model": llama_name,
                "llama_model_sha256": llama_sha256,
                "mmproj_model": mmproj_name,
                "mmproj_model_sha256": mmproj_sha256,
                "mtp_model": mtp_name,
                "mtp_model_sha256": mtp_sha256,
                "llama_spec_type": runtime[
                    "LLAMA_SPEC_TYPE"
                ],
                "llama_spec_draft_n_max": runtime[
                    "LLAMA_SPEC_DRAFT_N_MAX"
                ],
            },
        )

        write_checksums(
            root
        )

        with zipfile.ZipFile(
            archive,
            mode="x",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as output:
            for path in sorted(
                root.rglob("*")
            ):
                if not path.is_file():
                    continue

                member = (
                    Path(root.name)
                    / path.relative_to(root)
                )

                output.write(
                    path,
                    arcname=member.as_posix(),
                )

    print()
    print(
        "OFFLINE MODEL PACKAGE BUILD PASS"
    )
    print(
        f"package={archive}"
    )
    print(
        f"model_bundle_version={version}"
    )

    return archive


def verify(
    archive: Path,
) -> dict[str, str]:
    if not archive.is_file():
        raise RuntimeError(
            f"model package not found: {archive}"
        )

    if archive.suffix.lower() != ".zip":
        raise RuntimeError(
            "model package must be a ZIP file"
        )

    expected_root = archive.stem

    if not expected_root.startswith(
        "chatbot-models-"
    ):
        raise RuntimeError(
            "invalid model package filename"
        )

    expected_version = expected_root[
        len("chatbot-models-"):
    ]

    _validate_version(
        expected_version
    )

    with zipfile.ZipFile(
        archive,
        mode="r",
    ) as source:
        members = {
            info.filename: info
            for info in source.infolist()
            if not info.is_dir()
        }

        for name in members:
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
            if required not in members:
                raise RuntimeError(
                    f"missing model package file: "
                    f"{required}"
                )

        manifest = _parse_values(
            source.read(
                manifest_member
            ).decode("utf-8"),
            "model manifest",
        )

        required_manifest = (
            "model_bundle_version",
            "llama_model",
            "llama_model_sha256",
            "mmproj_model",
            "mmproj_model_sha256",
            "mtp_model",
            "mtp_model_sha256",
            "llama_spec_type",
            "llama_spec_draft_n_max",
        )

        missing = [
            key
            for key in required_manifest
            if not manifest.get(key)
        ]

        if missing:
            raise RuntimeError(
                "model manifest missing: "
                + ", ".join(missing)
            )

        if (
            manifest["model_bundle_version"]
            != expected_version
        ):
            raise RuntimeError(
                "model package filename/version mismatch"
            )

        checksums = _parse_checksums(
            source.read(
                checksum_member
            ).decode("utf-8")
        )

        actual_checksums: dict[str, str] = {}

        for relative, expected in checksums.items():
            relative_path = PurePosixPath(
                relative
            )

            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
            ):
                raise RuntimeError(
                    f"unsafe checksum path: {relative}"
                )

            member = (
                f"{expected_root}/"
                f"{relative}"
            )

            if member not in members:
                raise RuntimeError(
                    f"checksummed file missing: "
                    f"{relative}"
                )

            with source.open(
                member,
                mode="r",
            ) as handle:
                actual = _stream_digest(
                    handle
                )

            if actual != expected:
                raise RuntimeError(
                    f"checksum mismatch: {relative}"
                )

            actual_checksums[
                relative
            ] = actual

        for (
            name_key,
            digest_key,
        ) in (
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
            name = manifest[
                name_key
            ]

            if Path(name).name != name:
                raise RuntimeError(
                    f"invalid model name: {name}"
                )

            relative = (
                f"models/{name}"
            )

            actual = actual_checksums.get(
                relative
            )

            if not actual:
                raise RuntimeError(
                    f"model is not checksummed: {name}"
                )

            if (
                actual
                != manifest[digest_key]
            ):
                raise RuntimeError(
                    f"manifest digest mismatch: {name}"
                )

    print()
    print(
        "OFFLINE MODEL PACKAGE VERIFY PASS"
    )
    print(
        f"package={archive}"
    )
    print(
        "model_bundle_version="
        f"{manifest['model_bundle_version']}"
    )

    return manifest
