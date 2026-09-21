"""API, policy, streaming, and gateway acceptance."""

from __future__ import annotations

import json
import sys
from uuid import uuid4

from .client import (
    chat_result,
    expect_status,
    json_body,
    request,
    require_stream,
    stream_events,
)

from .config import (
    GATEWAY_URL,
    INTERNAL_URL,
)

from .proc import (
    authenticated_env,
    compose,
    require_runtime_files,
    run,
)

def config_check() -> None:
    require_runtime_files()

    compose(
        "config",
        "--quiet",
    )

    print(
        "PASS compose configuration"
    )

def auth_check() -> None:
    run(
        sys.executable,
        "-m",
        "tools.auth",
        "check",
        env=authenticated_env(),
    )


def unit_tests() -> None:
    run(
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests/unit",
        "-t",
        ".",
        "-p",
        "test_*.py",
        "-v",
    )


def compile_tests() -> None:
    code = r'''
from pathlib import Path

files = sorted(
    Path("tests").rglob("*.py")
)

for path in files:
    compile(
        path.read_text(
            encoding="utf-8"
        ),
        str(path),
        "exec",
    )

print(
    f"TEST PYTHON COMPILE OK ({len(files)} files)"
)
'''

    run(
        sys.executable,
        "-c",
        code,
    )


def policy_tests() -> None:
    env = authenticated_env()

    for calibration in (
        "tests/data/domain_calibration.json",
        "tests/data/domain_boundary_calibration.json",
    ):
        run(
            sys.executable,
            "-m",
            "tests.integration.test_domain_policy_api",
            calibration,
            env=env,
        )


def runtime_python_compile() -> None:
    code = (
        "from pathlib import Path; "
        "roots=[Path('/app/chatbot_app'),"
        "Path('/app/pipelines')]; "
        "files=sorted("
        "p for root in roots "
        "for p in root.rglob('*.py')); "
        "[compile("
        "p.read_text(encoding='utf-8'),"
        "str(p),'exec'"
        ") for p in files]; "
        "print("
        "f'PYTHON COMPILE OK "
        "({len(files)} files)'"
        ")"
    )

    compose(
        "exec",
        "-T",
        "chatbot",
        "python",
        "-c",
        code,
    )


def policy_routing_suite() -> None:
    cases = (
        (
            "prepared-standard",
            (
                "FST cao hay thấp phản ánh mối quan hệ "
                "di truyền như thế nào giữa các quần thể?"
            ),
            "prepared_answer",
            "in_domain",
            "standard",
        ),
        (
            "prepared-high-risk-guard",
            (
                "Điểm trùng khớp ADN trên HV1, HV2, HV3 "
                "cần đạt bao nhiêu để xác nhận quan hệ "
                "huyết thống?"
            ),
            "evidence_limitation",
            "in_domain",
            "high",
        ),
        (
            "high-risk-no-diacritics",
            (
                "Xac nhan nguoi A co phai cha ruot "
                "cua nguoi B khong."
            ),
            "evidence_limitation",
            "in_domain",
            "high",
        ),
        (
            "out-of-domain",
            "Hướng dẫn tôi nấu phở bò.",
            "out_of_domain",
            "out_of_domain",
            "standard",
        ),
        (
            "clarification",
            "Phân tích kết quả này.",
            "clarification",
            "clarify",
            "standard",
        ),
    )

    for (
        name,
        message,
        expected_source,
        expected_domain,
        expected_risk,
    ) in cases:
        result = chat_result(
            message
        )

        decision = result.get(
            "decision"
        )

        if not isinstance(
            decision,
            dict,
        ):
            raise RuntimeError(
                f"{name}: decision missing"
            )

        actual = (
            result.get(
                "source"
            ),
            decision.get(
                "domain"
            ),
            decision.get(
                "risk"
            ),
        )

        expected = (
            expected_source,
            expected_domain,
            expected_risk,
        )

        if actual != expected:
            raise RuntimeError(
                f"{name}: expected={expected}, "
                f"actual={actual}"
            )

        print(
            f"PASS {name}: "
            f"{expected_source}/"
            f"{expected_domain}/"
            f"{expected_risk}"
        )

    print(
        "POLICY ROUTING ACCEPTANCE PASS"
    )


def api_contract_suite() -> None:
    status, _, _ = request(
        INTERNAL_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "STR là gì?",
        },
    )

    expect_status(
        "missing auth",
        status,
        401,
    )

    status, _, _ = request(
        INTERNAL_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "STR là gì?",
        },
        extra_headers={
            "Authorization": (
                "Bearer "
                + ("invalid-" * 8)
            ),
        },
    )

    expect_status(
        "invalid auth",
        status,
        401,
    )

    status, _, _ = request(
        INTERNAL_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "STR là gì?",
            "conversation_id": (
                "not-a-uuid"
            ),
        },
        authenticated=True,
    )

    expect_status(
        "invalid conversation_id",
        status,
        422,
    )

    result = chat_result(
        (
            "FST cao hay thấp phản ánh "
            "mối quan hệ di truyền như thế nào "
            "giữa các quần thể?"
        )
    )

    if (
        "conversation_id" in result
        or "turn" in result
    ):
        raise RuntimeError(
            "stateless request was persisted"
        )

    print(
        "PASS authenticated stateless request"
    )

    print(
        "API CONTRACT ACCEPTANCE PASS"
    )


def public_api_suite() -> None:
    status, _, _ = request(
        GATEWAY_URL,
        "/ready",
    )

    expect_status(
        "public readiness requires auth",
        status,
        401,
    )

    status, _, raw = request(
        GATEWAY_URL,
        "/ready",
        authenticated=True,
    )

    expect_status(
        "public authenticated readiness",
        status,
        200,
    )

    ready = json_body(raw)

    if ready.get("status") != "ready":
        raise RuntimeError(
            f"unexpected readiness response: {ready}"
        )

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": "STR là gì?",
        },
    )

    expect_status(
        "public chat requires auth",
        status,
        401,
    )

    status, _, raw = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "FST cao hay thấp phản ánh "
                "mối quan hệ di truyền như thế nào "
                "giữa các quần thể?"
            ),
        },
        authenticated=True,
    )

    expect_status(
        "public stateless chat",
        status,
        200,
    )

    result = json_body(raw)

    if "result" in result:
        raise RuntimeError(
            "public API leaked Hayhooks result envelope"
        )

    for key in (
        "answer",
        "source",
        "decision",
        "evidence_status",
        "citations",
    ):
        if key not in result:
            raise RuntimeError(
                f"public chat response missing {key}"
            )

    if (
        "conversation_id" in result
        or "turn" in result
    ):
        raise RuntimeError(
            "stateless public request was persisted"
        )

    print(
        "PASS public response contract"
    )

    conversation_id = str(
        uuid4()
    )

    for message in (
        "STR là gì?",
        "FST có ý nghĩa gì trong di truyền quần thể?",
    ):
        status, _, raw = request(
            GATEWAY_URL,
            "/api/v1/chat",
            method="POST",
            body={
                "message": message,
                "conversation_id": conversation_id,
            },
            authenticated=True,
        )

        expect_status(
            "public stateful chat",
            status,
            200,
        )

        result = json_body(raw)

        if (
            result.get("conversation_id")
            != conversation_id
        ):
            raise RuntimeError(
                "public conversation_id changed"
            )

    status, headers, raw = request(
        GATEWAY_URL,
        "/api/v1/chat/stream",
        method="POST",
        body={
            "message": (
                "FST cao hay thấp phản ánh "
                "mối quan hệ di truyền như thế nào "
                "giữa các quần thể?"
            ),
        },
        authenticated=True,
        timeout=180,
    )

    expect_status(
        "public SSE chat",
        status,
        200,
    )

    content_type = headers.get(
        "Content-Type",
        "",
    )

    if not content_type.startswith(
        "text/event-stream"
    ):
        raise RuntimeError(
            "public stream is not SSE"
        )

    stream = raw.decode(
        "utf-8"
    )

    for event_type in (
        '"type":"start"',
        '"type":"chunk"',
        '"type":"end"',
    ):
        if event_type not in stream:
            raise RuntimeError(
                "public stream missing "
                + event_type
            )

    status, _, raw = request(
        GATEWAY_URL,
        (
            "/api/v1/conversations/"
            + conversation_id
        ),
        method="DELETE",
        authenticated=True,
    )

    expect_status(
        "public conversation delete",
        status,
        200,
    )

    deleted = json_body(raw)

    if deleted.get(
        "deleted_turns"
    ) != 2:
        raise RuntimeError(
            "expected 2 deleted turns, got "
            f"{deleted!r}"
        )

    print(
        "PUBLIC API ACCEPTANCE PASS"
    )


def internal_security_suite() -> None:
    status, _, _ = request(
        INTERNAL_URL,
        "/status",
    )

    expect_status(
        "internal status",
        status,
        200,
    )

    status, _, _ = request(
        INTERNAL_URL,
        "/healthcheck/run",
        method="POST",
        body={},
    )

    expect_status(
        "internal readiness",
        status,
        200,
    )

    for path in (
        "/deploy-yaml",
        "/deploy_files",
        "/undeploy/chat",
    ):
        status, _, _ = request(
            INTERNAL_URL,
            path,
            method="POST",
            body={},
            authenticated=True,
        )

        expect_status(
            f"runtime management blocked {path}",
            status,
            404,
        )

    print(
        "INTERNAL SECURITY ACCEPTANCE PASS"
    )


def gateway_suite() -> None:
    status, headers, _ = request(
        GATEWAY_URL,
        "/live",
    )

    expect_status(
        "gateway liveness",
        status,
        200,
    )

    expected_headers = {
        "X-Content-Type-Options": (
            "nosniff"
        ),
        "X-Frame-Options": "DENY",
        "Referrer-Policy": (
            "no-referrer"
        ),
    }

    for name, expected in (
        expected_headers.items()
    ):
        actual = headers.get(
            name
        )

        if actual != expected:
            raise RuntimeError(
                f"security header {name}: "
                f"expected={expected!r}, "
                f"actual={actual!r}"
            )

    print(
        "PASS gateway security headers"
    )

    status, _, _ = request(
        GATEWAY_URL,
        "/ready",
        authenticated=True,
    )

    expect_status(
        "gateway readiness",
        status,
        200,
    )

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "Hướng dẫn tôi nấu phở."
            )
        },
    )

    expect_status(
        "gateway chat requires auth",
        status,
        401,
    )

    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "Hướng dẫn tôi nấu phở."
            )
        },
        authenticated=True,
    )

    expect_status(
        "authenticated gateway chat",
        status,
        200,
    )

    for path in (
        "/status",
        "/classify/run",
        "/deploy-yaml",
        "/chat/run",
        "/chat/stream",
        "/healthcheck/run",
    ):
        status, _, _ = request(
            GATEWAY_URL,
            path,
            method=(
                "GET"
                if path == "/status"
                else "POST"
            ),
            body=(
                None
                if path == "/status"
                else {}
            ),
            authenticated=(
                path != "/status"
            ),
        )

        expect_status(
            f"gateway blocks {path}",
            status,
            404,
        )

    # Chat endpoints intentionally accept larger request
    # bodies for base64 image input. Oversized text that
    # is still below the gateway body limit must therefore
    # reach application validation.
    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "x" * 70000
            )
        },
        authenticated=True,
    )

    expect_status(
        "oversized text rejected by application",
        status,
        422,
    )

    # The gateway must still enforce the dedicated 10 MiB
    # chat request limit before forwarding excessive bodies.
    status, _, _ = request(
        GATEWAY_URL,
        "/api/v1/chat",
        method="POST",
        body={
            "message": (
                "x" * (11 * 1024 * 1024)
            )
        },
        authenticated=True,
    )

    expect_status(
        "gateway chat body limit enforced",
        status,
        413,
    )

    print(
        "GATEWAY ACCEPTANCE PASS"
    )


def stream_suite(
    base_url: str,
    *,
    label: str,
) -> None:
    events = stream_events(
        (
            "Giải thích khái niệm "
            "heterozygosity trong di truyền "
            "quần thể."
        ),
        base_url=base_url,
    )

    _, _ = require_stream(
        events
    )

    chunks = sum(
        1
        for event in events
        if event.get(
            "type"
        )
        == "chunk"
    )

    print(
        f"PASS {label} SSE stream "
        f"-> {chunks} chunks"
    )
