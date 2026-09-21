"""Universal offline CPU + NVIDIA runtime release."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .env import (
    read_env,
    require,
)
from .image import (
    build as build_image,
    inspect_label,
    require_image,
    save,
    tag,
)
from .manifest import (
    read_manifest,
    verify_checksums,
    write_checksums,
    write_manifest,
)
from .source import (
    export_commit,
    inspect_source,
)


def _copy_tree(
    source: Path,
    target: Path,
) -> None:
    shutil.copytree(
        source,
        target,
    )


def _rewrite_versions(
    path: Path,
    images: dict[str, str],
) -> None:
    lines = []

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        key = line.partition("=")[0]

        if key in images:
            line = (
                f"{key}="
                f"{images[key]}"
            )

        lines.append(line)

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _release_compose(
    source: Path,
    target: Path,
) -> None:
    text = source.read_text(
        encoding="utf-8"
    )

    required_compose = (
        "name: chatbot",
        "container_name: chatbot-postgres",
        "container_name: chatbot-llama",
        "container_name: chatbot-app",
        "container_name: chatbot-proxy",
    )

    for value in required_compose:
        if value not in text:
            raise RuntimeError(
                "source compose requirement missing: "
                f"{value}"
            )
    old = (
        '    ports:\n'
        '      - "127.0.0.1:1416:1416"\n'
    )

    new = (
        '    expose:\n'
        '      - "1416"\n'
    )

    if old not in text:
        raise RuntimeError(
            "chatbot host-port block not found"
        )

    text = text.replace(
        old,
        new,
        1,
    )

    target.write_text(
        text,
        encoding="utf-8",
    )


def _zip_tree(
    root: Path,
    archive: Path,
) -> None:
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


def build(
    version: str | None = None,
    dist: Path = Path("dist"),
) -> Path:
    source = inspect_source()

    if source.state != "clean":
        raise RuntimeError(
            "runtime release requires a clean committed Git HEAD"
        )

    runtime = read_env(
        Path(".env.example")
    )

    values = read_env(
        Path(".env"),
        Path("versions.env"),
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
        values,
        "HAYHOOKS_IMAGE",
        "LLAMA_CPU_IMAGE",
        "LLAMA_GPU_IMAGE",
        "POSTGRES_IMAGE",
        "NGINX_IMAGE",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSION",
    )

    version = (
        version
        or os.environ.get(
            "RELEASE_VERSION"
        )
        or source.short_sha
    )

    dist.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive = (
        dist
        / f"chatbot-{version}.zip"
    )

    if archive.exists():
        raise RuntimeError(
            f"release already exists: {archive}"
        )

    source_images = {
        "LLAMA_CPU_IMAGE": values[
            "LLAMA_CPU_IMAGE"
        ],
        "LLAMA_GPU_IMAGE": values[
            "LLAMA_GPU_IMAGE"
        ],
        "POSTGRES_IMAGE": values[
            "POSTGRES_IMAGE"
        ],
        "NGINX_IMAGE": values[
            "NGINX_IMAGE"
        ],
    }

    release_images = {
        "CHATBOT_IMAGE": (
            f"chatbot-app:{version}"
        ),
        "LLAMA_CPU_IMAGE": (
            f"chatbot-llama-cpu:{version}"
        ),
        "LLAMA_GPU_IMAGE": (
            f"chatbot-llama-gpu:{version}"
        ),
        "POSTGRES_IMAGE": (
            f"chatbot-postgres:{version}"
        ),
        "NGINX_IMAGE": (
            f"chatbot-nginx:{version}"
        ),
    }

    for image in source_images.values():
        require_image(image)

    for key, image in source_images.items():
        tag(
            image,
            release_images[key],
        )

    with tempfile.TemporaryDirectory(
        prefix=".chatbot-release-",
        dir=dist,
    ) as temporary:
        temporary_root = Path(temporary)

        build_context = (
            temporary_root
            / "source"
        )

        export_commit(
            source.sha,
            build_context,
        )

        committed_values = read_env(
            build_context / "versions.env"
        )

        require(
            committed_values,
            "HAYHOOKS_IMAGE",
            "EMBEDDING_MODEL",
            "EMBEDDING_DIMENSION",
        )

        revision_label = (
            "org.opencontainers.image.revision"
        )

        build_image(
            release_images[
                "CHATBOT_IMAGE"
            ],
            build_context,
            build_args={
                "HAYHOOKS_IMAGE": committed_values[
                    "HAYHOOKS_IMAGE"
                ],
                "EMBEDDING_MODEL": committed_values[
                    "EMBEDDING_MODEL"
                ],
                "EMBEDDING_DIMENSION": committed_values[
                    "EMBEDDING_DIMENSION"
                ],
            },
            labels={
                revision_label: source.sha,
            },
        )

        actual_revision = inspect_label(
            release_images[
                "CHATBOT_IMAGE"
            ],
            revision_label,
        )

        if actual_revision != source.sha:
            raise RuntimeError(
                "built chatbot image revision mismatch: "
                f"expected={source.sha} "
                f"actual={actual_revision}"
            )

        root = (
            Path(temporary)
            / f"chatbot-{version}"
        )

        root.mkdir()

        _release_compose(
            Path("compose.yaml"),
            root / "compose.yaml",
        )

        shutil.copy2(
            "compose.gpu.yaml",
            root / "compose.gpu.yaml",
        )

        shutil.copy2(
            ".env.example",
            root / ".env.example",
        )

        shutil.copy2(
            "versions.env",
            root / "versions.env",
        )

        _rewrite_versions(
            root / "versions.env",
            release_images,
        )

        (
            root
            / "versions.gpu.env"
        ).write_text(
            (
                "LLAMA_GPU_IMAGE="
                f"{release_images['LLAMA_GPU_IMAGE']}\n"
            ),
            encoding="utf-8",
        )

        shutil.copy2(
            "offline/Makefile.release",
            root / "Makefile",
        )

        _copy_tree(
            Path("offline"),
            root / "offline",
        )

        (
            root
            / "offline/Makefile.release"
        ).unlink()

        _copy_tree(
            Path("nginx"),
            root / "nginx",
        )

        _copy_tree(
            Path("pipelines"),
            root / "pipelines",
        )

        _copy_tree(
            Path("database"),
            root / "database",
        )

        (
            root
            / "data"
        ).mkdir()

        _copy_tree(
            Path("data/documents"),
            root / "data/documents",
        )

        _copy_tree(
            Path("data/figures"),
            root / "data/figures",
        )

        images = (
            root
            / "images"
        )

        save(
            release_images[
                "CHATBOT_IMAGE"
            ],
            images / "chatbot.tar",
        )

        save(
            release_images[
                "LLAMA_CPU_IMAGE"
            ],
            images / "llama-cpu.tar",
        )

        save(
            release_images[
                "LLAMA_GPU_IMAGE"
            ],
            images / "llama-gpu.tar",
        )

        save(
            release_images[
                "POSTGRES_IMAGE"
            ],
            images / "postgres.tar",
        )

        save(
            release_images[
                "NGINX_IMAGE"
            ],
            images / "nginx.tar",
        )

        write_manifest(
            root / "BUNDLE-MANIFEST.txt",
            {
                "bundle_type": "universal",
                "bundle_version": version,
                "source_git_sha": source.sha,
                "source_state": source.state,
                "chatbot_image_revision": source.sha,
                "architecture": (
                    source.architecture
                ),
                "required_model_bundle": runtime[
                    "MODEL_BUNDLE_VERSION"
                ],
                "llama_model": runtime[
                    "LLAMA_MODEL_NAME"
                ],
                "mmproj_model": runtime[
                    "MMPROJ_MODEL"
                ],
                "mtp_model": runtime[
                    "MTP_MODEL_NAME"
                ],
                "llama_spec_type": runtime[
                    "LLAMA_SPEC_TYPE"
                ],
                "llama_spec_draft_n_max": runtime[
                    "LLAMA_SPEC_DRAFT_N_MAX"
                ],
                "chatbot_image": release_images[
                    "CHATBOT_IMAGE"
                ],
                "llama_cpu_image": release_images[
                    "LLAMA_CPU_IMAGE"
                ],
                "llama_gpu_image": release_images[
                    "LLAMA_GPU_IMAGE"
                ],
                "postgres_image": release_images[
                    "POSTGRES_IMAGE"
                ],
                "nginx_image": release_images[
                    "NGINX_IMAGE"
                ],
                "embedding_model": values[
                    "EMBEDDING_MODEL"
                ],
                "embedding_dimension": values[
                    "EMBEDDING_DIMENSION"
                ],
            },
        )

        write_checksums(root)

        _zip_tree(
            root,
            archive,
        )

    print()
    print(
        "UNIVERSAL OFFLINE RELEASE BUILD PASS"
    )
    print(
        f"release={archive}"
    )
    print(
        "required_model_bundle="
        f"{runtime['MODEL_BUNDLE_VERSION']}"
    )

    return archive


def _safe_extract(
    archive: Path,
    destination: Path,
) -> Path:
    expected_root = archive.stem

    with zipfile.ZipFile(
        archive,
        mode="r",
    ) as source:
        for info in source.infolist():
            path = PurePosixPath(
                info.filename
            )

            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0]
                != expected_root
            ):
                raise RuntimeError(
                    "unsafe release ZIP member: "
                    f"{info.filename}"
                )

        source.extractall(
            destination
        )

    root = (
        destination
        / expected_root
    )

    if not root.is_dir():
        raise RuntimeError(
            "release root is missing"
        )

    return root


def verify(
    archive: Path,
) -> dict[str, str]:
    if not archive.is_file():
        raise RuntimeError(
            f"release not found: {archive}"
        )

    if (
        not archive.name.startswith(
            "chatbot-"
        )
        or archive.suffix.lower()
        != ".zip"
    ):
        raise RuntimeError(
            "invalid universal release filename"
        )

    with tempfile.TemporaryDirectory(
        prefix=".chatbot-verify-"
    ) as temporary:
        root = _safe_extract(
            archive,
            Path(temporary),
        )

        required = (
            "Makefile",
            "compose.yaml",
            "compose.gpu.yaml",
            "versions.env",
            "versions.gpu.env",
            ".env.example",
            "BUNDLE-MANIFEST.txt",
            "SHA256SUMS",
            "images/chatbot.tar",
            "images/llama-cpu.tar",
            "images/llama-gpu.tar",
            "images/postgres.tar",
            "images/nginx.tar",
            "offline/install.sh",
            "offline/manage.sh",
            "offline/lib/common.sh",
            "offline/lib/check.py",
            "offline/lib/accept.sh",
            "offline/lib/host.sh",
            "offline/lib/models.py",
            "nginx/nginx.conf",
            "pipelines",
            "database",
            "data/documents",
        )

        for relative in required:
            if not (
                root / relative
            ).exists():
                raise RuntimeError(
                    "required release path "
                    f"is missing: {relative}"
                )

        if (
            root / ".env"
        ).exists():
            raise RuntimeError(
                "private .env included in release"
            )

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if (
                path.suffix.lower()
                == ".gguf"
            ):
                raise RuntimeError(
                    "GGUF model included in "
                    "runtime release"
                )

            parts = path.relative_to(
                root
            ).parts

            if (
                "runtime" in parts
                and "secrets" in parts
            ):
                raise RuntimeError(
                    "runtime secrets included "
                    "in release"
                )

        verify_checksums(root)

        manifest = read_manifest(
            root / "BUNDLE-MANIFEST.txt"
        )

        if (
            manifest.get("bundle_type")
            != "universal"
        ):
            raise RuntimeError(
                "release is not universal"
            )

        if (
            manifest.get("source_state")
            != "clean"
        ):
            raise RuntimeError(
                "release source is not clean"
            )

        source_git_sha = manifest.get(
            "source_git_sha",
            "",
        )

        if not source_git_sha:
            raise RuntimeError(
                "release source Git SHA is missing"
            )

        if manifest.get(
            "chatbot_image_revision"
        ) != source_git_sha:
            raise RuntimeError(
                "chatbot image revision does not match source Git SHA"
            )

        model_requirements = {
            "required_model_bundle": manifest.get(
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

        missing_model_requirements = [
            key
            for key, value
            in model_requirements.items()
            if not value
        ]

        if missing_model_requirements:
            raise RuntimeError(
                "release model requirements missing: "
                + ", ".join(
                    missing_model_requirements
                )
            )

        required_model_bundle = (
            model_requirements[
                "required_model_bundle"
            ]
        )

        version = manifest.get(
            "bundle_version",
            "",
        )

        expected_images = {
            "chatbot_image": (
                f"chatbot-app:{version}"
            ),
            "llama_cpu_image": (
                f"chatbot-llama-cpu:{version}"
            ),
            "llama_gpu_image": (
                f"chatbot-llama-gpu:{version}"
            ),
            "postgres_image": (
                f"chatbot-postgres:{version}"
            ),
            "nginx_image": (
                f"chatbot-nginx:{version}"
            ),
        }

        for key, expected in (
            expected_images.items()
        ):
            if manifest.get(key) != expected:
                raise RuntimeError(
                    "release image naming "
                    f"mismatch: {key}"
                )

        compose = (
            root / "compose.yaml"
        ).read_text(
            encoding="utf-8"
        )

        required_compose = (
            "name: chatbot",
            "container_name: chatbot-postgres",
            "container_name: chatbot-llama",
            "container_name: chatbot-app",
            "container_name: chatbot-proxy",
        )

        for value in required_compose:
            if value not in compose:
                raise RuntimeError(
                    "release compose naming "
                    f"missing: {value}"
                )

        if "127.0.0.1:1416:1416" in compose:
            raise RuntimeError(
                "release publishes chatbot "
                "maintenance port"
            )

    print()
    print(
        "UNIVERSAL OFFLINE RELEASE VERIFY PASS"
    )
    print(
        f"release={archive}"
    )
    print(
        "required_model_bundle="
        f"{required_model_bundle}"
    )

    return manifest
