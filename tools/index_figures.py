"""Incrementally precompute configured figure descriptions."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from chatbot_app.database import (
    postgres_connection_string,
    read_secret,
    required_env,
)
from chatbot_app.figures import (
    FigureAsset,
    scan_figures,
)


FIGURE_DESCRIPTION_PROMPT = "\n".join(
    [
        "Phân tích hình ảnh khoa học này bằng tiếng Việt.",
        "Nêu loại hình, nội dung chính, các trục, chú giải",
        "hoặc nhóm dữ liệu nhìn thấy, xu hướng hay mối",
        "quan hệ nổi bật và ý nghĩa khoa học có thể kết",
        "luận trực tiếp từ hình.",
        "Không suy diễn dữ liệu, nhãn hoặc kết luận không",
        "xuất hiện trong hình.",
        "Trả lời ngắn gọn nhưng đủ thông tin để dùng làm",
        "ngữ cảnh cho các câu hỏi tiếp theo về hình.",
    ]
)


@dataclass(
    frozen=True,
    slots=True,
)
class GeneratedFigure:
    asset: FigureAsset
    description: str


def description_version() -> int:
    raw = os.environ.get(
        "FIGURE_DESCRIPTION_VERSION",
        "1",
    ).strip()

    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(
            "FIGURE_DESCRIPTION_VERSION "
            "must be an integer"
        ) from error

    if value < 1:
        raise RuntimeError(
            "FIGURE_DESCRIPTION_VERSION "
            "must be positive"
        )

    return value


def generate_description(
    asset: FigureAsset,
) -> str:
    base_url = required_env(
        "LLAMA_BASE_URL"
    ).rstrip("/")

    model = required_env(
        "LLAMA_MODEL_ALIAS"
    )

    api_key = read_secret(
        "LLAMA_API_KEY_FILE"
    )

    raw = asset.path.read_bytes()

    encoded = base64.b64encode(
        raw
    ).decode("ascii")

    image_url = (
        f"data:{asset.mime_type};base64,"
        f"{encoded}"
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            FIGURE_DESCRIPTION_PROMPT
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512,
        "stream": False,
    }

    request = urllib.request.Request(
        (
            base_url
            + "/chat/completions"
        ),
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": (
                f"Bearer {api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=600,
        ) as response:
            result = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )
    except urllib.error.HTTPError as error:
        body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "Figure description request "
            f"failed: HTTP {error.code}: "
            f"{body[:500]}"
        ) from error

    try:
        description = (
            result["choices"][0][
                "message"
            ]["content"]
        ).strip()
    except (
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
    ) as error:
        raise RuntimeError(
            "Invalid llama.cpp figure "
            "description response"
        ) from error

    if not description:
        raise RuntimeError(
            "Empty figure description"
        )

    return description


def main() -> None:
    figure_dir = Path(
        os.environ.get(
            "FIGURE_DIR",
            "/data/figures",
        )
    )

    version = description_version()

    assets = scan_figures(
        figure_dir
    )

    asset_by_id = {
        asset.figure_id: asset
        for asset in assets
    }

    connection = psycopg.connect(
        postgres_connection_string(),
        row_factory=dict_row,
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    figure_id,
                    content_hash,
                    description_version
                FROM figure_descriptions
                """
            )

            existing_rows = (
                cursor.fetchall()
            )

        existing = {
            str(row["figure_id"]): row
            for row in existing_rows
        }

        changed: list[
            FigureAsset
        ] = []

        reused = 0

        for asset in assets:
            current = existing.get(
                asset.figure_id
            )

            if (
                current is not None
                and current[
                    "content_hash"
                ]
                == asset.content_hash
                and int(
                    current[
                        "description_version"
                    ]
                )
                == version
            ):
                reused += 1
                continue

            changed.append(
                asset
            )

        generated: list[
            GeneratedFigure
        ] = []

        for position, asset in enumerate(
            changed,
            start=1,
        ):
            print(
                "figure_compute="
                f"{position}/{len(changed)} "
                f"id={asset.figure_id}",
                flush=True,
            )

            description = (
                generate_description(
                    asset
                )
            )

            generated.append(
                GeneratedFigure(
                    asset=asset,
                    description=description,
                )
            )

        discovered_ids = set(
            asset_by_id
        )

        stale_ids = (
            set(existing)
            - discovered_ids
        )

        created = sum(
            item.asset.figure_id
            not in existing
            for item in generated
        )

        updated = (
            len(generated)
            - created
        )

        # No database mutation occurs until every required
        # vision generation succeeded. Existing descriptions
        # therefore remain available while indexing runs.
        with connection.transaction():
            with connection.cursor() as cursor:
                for item in generated:
                    cursor.execute(
                        """
                        INSERT INTO figure_descriptions (
                            figure_id,
                            content_hash,
                            mime_type,
                            source_name,
                            description_version,
                            description,
                            updated_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, now()
                        )
                        ON CONFLICT (figure_id)
                        DO UPDATE SET
                            content_hash =
                                EXCLUDED.content_hash,
                            mime_type =
                                EXCLUDED.mime_type,
                            source_name =
                                EXCLUDED.source_name,
                            description_version =
                                EXCLUDED.description_version,
                            description =
                                EXCLUDED.description,
                            updated_at = now()
                        """,
                        (
                            item.asset.figure_id,
                            item.asset.content_hash,
                            item.asset.mime_type,
                            item.asset.source_name,
                            version,
                            item.description,
                        ),
                    )

                if stale_ids:
                    cursor.execute(
                        """
                        DELETE FROM figure_descriptions
                        WHERE figure_id = ANY(%s)
                        """,
                        (
                            sorted(stale_ids),
                        ),
                    )

        print(
            f"figures_discovered={len(assets)}"
        )
        print(
            f"figures_reused={reused}"
        )
        print(
            f"figures_created={created}"
        )
        print(
            f"figures_updated={updated}"
        )
        print(
            f"figures_removed={len(stale_ids)}"
        )
        print(
            "FIGURE INDEX PASS"
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
