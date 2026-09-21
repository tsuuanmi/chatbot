"""Offline deployment checks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path


def digest(
    path: Path,
) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(
            1024 * 1024
        ):
            hasher.update(chunk)

    return hasher.hexdigest()


def checksum(
    root: Path,
) -> None:
    checksum_file = (
        root / "SHA256SUMS"
    )

    if not checksum_file.is_file():
        raise RuntimeError(
            "SHA256SUMS is missing"
        )

    for raw in checksum_file.read_text(
        encoding="utf-8"
    ).splitlines():
        if not raw.strip():
            continue

        expected, separator, name = (
            raw.partition("  ")
        )

        if not separator:
            raise RuntimeError(
                f"invalid checksum line: {raw!r}"
            )

        path = root / name

        if not path.is_file():
            raise RuntimeError(
                f"missing checksummed file: {name}"
            )

        if digest(path) != expected:
            raise RuntimeError(
                f"checksum mismatch: {name}"
            )

    print(
        "OFFLINE CHECKSUM PASS"
    )


def runtime(
    gateway: str,
    key_file: Path,
) -> None:
    gateway = gateway.rstrip("/")

    if not key_file.is_file():
        raise RuntimeError(
            "client API key is missing"
        )

    api_key = key_file.read_text(
        encoding="utf-8"
    ).strip()

    if not api_key:
        raise RuntimeError(
            "client API key is empty"
        )

    with urllib.request.urlopen(
        gateway + "/live",
        timeout=10,
    ) as response:
        if response.status != 200:
            raise RuntimeError(
                "liveness check failed"
            )

    request = urllib.request.Request(
        gateway + "/ready",
        headers={
            "Authorization": (
                "Bearer " + api_key
            ),
        },
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        body = json.load(response)

    if (
        not isinstance(body, dict)
        or body.get("status") != "ready"
    ):
        raise RuntimeError(
            f"service is not ready: {body}"
        )

    request = urllib.request.Request(
        gateway + "/api/v1/chat",
        data=json.dumps(
            {
                "message": (
                    "Hướng dẫn tôi nấu phở."
                )
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                "Bearer " + api_key
            ),
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        body = json.load(response)

    if (
        not isinstance(body, dict)
        or not isinstance(
            body.get("answer"),
            str,
        )
        or not body["answer"].strip()
    ):
        raise RuntimeError(
            "invalid authenticated chat response"
        )

    print(
        "OFFLINE VERIFY PASS"
    )


def media(
    gateway: str,
    key_file: Path,
    figure_dir: Path,
    pixel_image: Path,
) -> None:
    gateway = gateway.rstrip("/")

    if not key_file.is_file():
        raise RuntimeError(
            "client API key is missing"
        )

    api_key = key_file.read_text(
        encoding="utf-8"
    ).strip()

    if not api_key:
        raise RuntimeError(
            "client API key is empty"
        )

    if not figure_dir.is_dir():
        raise RuntimeError(
            f"figure directory is missing: {figure_dir}"
        )

    if not pixel_image.is_file():
        raise RuntimeError(
            f"pixel acceptance image is missing: {pixel_image}"
        )

    candidates = sorted(
        path
        for path in figure_dir.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in {".png", ".jpg", ".jpeg", ".webp"}
        )
    )

    if not candidates:
        raise RuntimeError(
            "configured figure inventory is empty"
        )

    figure_id = candidates[0].stem

    image = (
        "data:image/png;base64,"
        + base64.b64encode(
            pixel_image.read_bytes()
        ).decode("ascii")
    )

    def post(
        payload: dict[str, object],
    ) -> tuple[int, dict[str, object]]:
        req = urllib.request.Request(
            gateway + "/api/v1/chat",
            data=json.dumps(
                payload,
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req,
                timeout=300,
            ) as response:
                status = response.status
                raw = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read()

        if not raw:
            return status, {}

        value = json.loads(
            raw.decode("utf-8")
        )

        if not isinstance(value, dict):
            raise RuntimeError(
                "media response is not a JSON object"
            )

        return status, value

    def result(
        body: dict[str, object],
    ) -> dict[str, object]:
        return body

    status, _ = post({
        "message": "Giải thích hình này",
        "figure_id": "does-not-exist",
    })

    if status != 422:
        raise RuntimeError(
            f"unknown figure expected 422, got {status}"
        )

    status, _ = post({
        "message": (
            "FST có ý nghĩa gì trong di truyền quần thể?"
        ),
        "image": "%%%not-base64%%%",
    })

    if status != 422:
        raise RuntimeError(
            f"malformed base64 expected 422, got {status}"
        )

    status, _ = post({
        "message": "Giải thích hình này",
        "figure_id": figure_id,
        "image": image,
    })

    if status != 422:
        raise RuntimeError(
            f"figure/image conflict expected 422, got {status}"
        )

    status, body = post({
        "message": "Cách nấu phở bò ngon?",
        "image": image,
    })

    if status != 200:
        raise RuntimeError(
            f"OOD image request returned {status}"
        )

    value = result(body)
    decision = value.get("decision")

    if (
        not isinstance(decision, dict)
        or decision.get("domain") != "out_of_domain"
        or value.get("source") != "out_of_domain"
    ):
        raise RuntimeError(
            "image bypassed out-of-domain policy"
        )

    status, body = post({
        "message": (
            "Hãy kết luận mẫu hiện trường này "
            "có thuộc về nghi phạm hay không."
        ),
        "image": image,
    })

    if status != 200:
        raise RuntimeError(
            f"high-risk image request returned {status}"
        )

    value = result(body)
    decision = value.get("decision")

    if (
        not isinstance(decision, dict)
        or decision.get("risk") != "high"
        or value.get("source") != "evidence_limitation"
    ):
        raise RuntimeError(
            "image bypassed high-risk policy"
        )

    status, body = post({
        "message": "Giải thích hình này",
        "figure_id": figure_id,
    })

    if status != 200:
        raise RuntimeError(
            f"configured figure returned {status}"
        )

    value = result(body)

    if value.get("source") != "figure_prepared":
        raise RuntimeError(
            "configured figure fast path failed"
        )

    if value.get("figure_id") != figure_id:
        raise RuntimeError(
            "configured figure ID mismatch"
        )

    if value.get("citations") != []:
        raise RuntimeError(
            "configured figure returned unexpected citations"
        )

    query = (
        "FST có ý nghĩa gì trong di truyền quần thể? "
        "Hãy quan sát trực tiếp ảnh được cung cấp và "
        "liệt kê chính xác tất cả nhãn quần thể "
        "xuất hiện trên hai trục."
    )

    status, body = post({
        "message": query,
        "image": image,
    })

    if status != 200:
        raise RuntimeError(
            f"raw image request returned {status}"
        )

    value = result(body)
    decision = value.get("decision")

    if value.get("source") != "generated":
        raise RuntimeError(
            "raw image source was not generated"
        )

    if (
        not isinstance(decision, dict)
        or decision.get("domain") != "in_domain"
    ):
        raise RuntimeError(
            "raw image request was not in-domain"
        )

    answer = str(value.get("answer") or "")

    normalized = unicodedata.normalize(
        "NFKD",
        answer,
    )

    folded = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    folded = (
        folded
        .replace("đ", "d")
        .replace("Đ", "D")
        .lower()
    )

    expected = (
        "aa",
        "cauc",
        "hisp",
        "asian",
        "viet nam",
    )

    missing = [
        label
        for label in expected
        if label not in folded
    ]

    if missing:
        raise RuntimeError(
            "raw image model did not read pixel labels: "
            + ", ".join(missing)
        )

    print(
        "OFFLINE MEDIA ACCEPTANCE PASS"
    )

def main() -> None:
    parser = argparse.ArgumentParser()

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    checksum_parser = commands.add_parser(
        "checksum"
    )

    checksum_parser.add_argument(
        "root",
        type=Path,
    )

    runtime_parser = commands.add_parser(
        "runtime"
    )

    runtime_parser.add_argument(
        "gateway"
    )

    runtime_parser.add_argument(
        "key_file",
        type=Path,
    )

    media_parser = commands.add_parser(
        "media"
    )

    media_parser.add_argument(
        "gateway"
    )

    media_parser.add_argument(
        "key_file",
        type=Path,
    )

    media_parser.add_argument(
        "figure_dir",
        type=Path,
    )

    media_parser.add_argument(
        "pixel_image",
        type=Path,
    )

    args = parser.parse_args()

    if args.command == "checksum":
        checksum(
            args.root
        )
        return

    if args.command == "runtime":
        runtime(
            args.gateway,
            args.key_file,
        )
        return

    media(
        args.gateway,
        args.key_file,
        args.figure_dir,
        args.pixel_image,
    )


if __name__ == "__main__":
    main()
