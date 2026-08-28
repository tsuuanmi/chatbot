"""Live Docker-stack correctness tests for the answer-priority cascade.

Run with: pytest -m "integration and not performance"
Prerequisite: make start [ACCELERATOR=auto|cpu|gpu] (all services healthy)

Covers every response source: prepared_answer, generated (with and without
RAG), out_of_domain, rag, plus multi-turn context, streaming, and cleanup.

Each test prints the request it sends and the answer it receives so the
log is self-documenting.
"""

import json
import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080/api/v1")
API_KEY = os.getenv("TEST_API_KEY")
VERIFY: bool | str = os.getenv("TEST_CA_CERT", True)
AUTH_HEADERS = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
pytestmark = pytest.mark.integration


def _post(path: str, payload: dict, timeout: float = 30) -> dict:
    response = httpx.post(
        f"{BASE_URL}{path}",
        json=payload,
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _show(label: str, query: str, payload: dict) -> None:
    """Print the request and answer for the test log."""
    print(f"\n  [{label}]")
    print(f"  request:  {query}")
    print(f"  source:   {payload['source']}  status: {payload['conversation_status']}")
    print(f"  answer:   {payload['response']}")


def _clear(conversation_id: str) -> None:
    response = httpx.delete(
        f"{BASE_URL}/conversations/{conversation_id}",
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=10,
    )
    response.raise_for_status()


def test_live_health() -> None:
    response = httpx.get(
        f"{BASE_URL}/health/detailed",
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=10,
    )
    response.raise_for_status()
    assert response.json()["status"] == "healthy"


def test_live_prepared_answer() -> None:
    query = "Mẫu hài cốt có vị trí trên biểu đồ nhiệt như thế nào so với các nhóm dân tộc khác?"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-prepared", "query": query},
    )
    assert payload["source"] == "prepared_answer"
    assert payload["conversation_status"] == "active"
    assert payload["response"]
    _show("prepared_answer", query, payload)
    _clear("integration-prepared")


def test_live_generated_without_rag() -> None:
    query = "Vai trò của RNA trong biểu hiện gene là gì?"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-generated", "query": query},
    )
    assert payload["source"] == "generated"
    assert payload["conversation_status"] == "active"
    assert payload["response"]
    _show("generated (no RAG)", query, payload)
    _clear("integration-generated")


def test_live_generated_with_rag() -> None:
    query = "mtDNA là gì?"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-generated-rag", "query": query},
    )
    assert payload["source"] == "generated"
    assert payload["conversation_status"] == "active"
    assert payload["response"]
    _show("generated (with RAG)", query, payload)
    _clear("integration-generated-rag")


def test_live_long_mtdna_prompt_within_embedding_context() -> None:
    query = (
        "Phân tích phân bố variants mtDNA giữa HV1, HV2 và HV3: "
        + " ".join(f"chrM:{16000 + index}=G" for index in range(200))
    )
    payload = _post(
        "/chat",
        {"conversation_id": "integration-long-mtdna", "query": query},
        timeout=120,
    )
    assert payload["source"] in {"generated", "clarification"}
    assert payload["conversation_status"] == "active"
    assert payload["response"]
    _show("long mtDNA prompt", query, payload)
    _clear("integration-long-mtdna")


def test_live_neutral_follow_up_uses_in_domain_history() -> None:
    conversation_id = "integration-multi-turn"
    first_query = "DNA là gì?"
    first = _post("/chat", {"conversation_id": conversation_id, "query": first_query})
    assert first["source"] in {"prepared_answer", "generated"}

    follow_up = "Cấu trúc của nó?"
    second = _post("/chat", {"conversation_id": conversation_id, "query": follow_up})
    assert second["source"] == "generated"
    assert second["conversation_status"] == "active"
    assert second["response"]
    assert "ngoài phạm vi" not in second["response"].lower()
    _show("multi-turn follow-up", follow_up, second)

    third_query = "Cho ví dụ?"
    third = _post("/chat", {"conversation_id": conversation_id, "query": third_query})
    assert third["source"] == "generated"
    assert third["conversation_status"] == "active"
    assert third["response"]
    assert "ngoài phạm vi" not in third["response"].lower()
    _show("chained follow-up", third_query, third)
    _clear(conversation_id)


@pytest.mark.parametrize(
    "query",
    [
        "Bóng đá là gì?",
        "Cách dùng AI để nấu ăn?",
        "Phân tích dữ liệu bóng đá",
        "Phần mềm chỉnh sửa ảnh nào tốt?",
        "Công nghệ AI là gì?",
    ],
)
def test_live_out_of_domain_query_is_rejected(query: str) -> None:
    payload = _post(
        "/chat",
        {"conversation_id": "integration-out-of-domain", "query": query},
        timeout=10,
    )
    assert payload["source"] == "out_of_domain"
    assert payload["conversation_status"] == "ended"
    assert "ngoài phạm vi" in payload["response"]
    _show("out_of_domain", query, payload)
    _clear("integration-out-of-domain")


def test_live_ambiguous_query_requests_clarification() -> None:
    query = "Phân tích kết quả này"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-clarify", "query": query},
        timeout=10,
    )
    assert payload["source"] == "clarification"
    assert payload["conversation_status"] == "active"
    assert "bổ sung ngữ cảnh" in payload["response"]
    _clear("integration-clarify")


def test_live_high_risk_request_abstains_without_authoritative_evidence() -> None:
    query = "Kết luận mẫu hiện trường này thuộc về nghi phạm"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-high-risk", "query": query},
    )
    assert payload["source"] == "generated"
    assert "không thể đưa ra kết luận" in payload["response"]
    assert payload["citations"] == []
    _clear("integration-high-risk")


def test_live_figure_explanation() -> None:
    query = "Giải thích nội dung của hình này"
    payload = _post(
        "/chat",
        {
            "conversation_id": "integration-figure",
            "query": query,
            "figure_id": "heatmap1",
        },
    )
    assert payload["source"] == "figure_prepared"
    assert payload["conversation_status"] == "active"
    assert payload["response"]
    assert payload["citations"] == []
    assert "image" not in payload
    _show("figure (heatmap1)", f"{query} [figure_id=heatmap1]", payload)
    _clear("integration-figure")


def test_live_generated_chat_streams_json_tokens() -> None:
    query = "Giải thích STR là gì?"
    with httpx.stream(
        "POST",
        f"{BASE_URL}/chat/stream",
        json={"conversation_id": "integration-stream", "query": query},
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=60,
    ) as response:
        response.raise_for_status()
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    assert events[0]["type"] == "start"
    assert events[0]["source"] == "generated"
    assert sum(event["type"] == "chunk" for event in events) > 1
    assert events[-1]["type"] == "end"
    streamed = "".join(event.get("content", "") for event in events)
    print("\n  [stream]")
    print(f"  request:  {query}")
    print("  source:   generated")
    print(f"  answer:   {streamed}")
    _clear("integration-stream")


def test_live_generated_answer_exposes_used_citation_provenance() -> None:
    query = "Trong trường hợp nào dữ liệu STR nên được ưu tiên trong giám định?"
    payload = _post(
        "/chat",
        {"conversation_id": "integration-citations", "query": query},
    )
    assert payload["source"] == "generated"
    assert payload["response"]
    assert payload["citations"]
    cited_ids = {citation["id"] for citation in payload["citations"]}
    assert all(f"[{citation_id}]" in payload["response"] for citation_id in cited_ids)
    assert all(
        citation["source"]["approval_status"] == "approved"
        for citation in payload["citations"]
    )
    _show("grounded_chat", query, payload)
    _clear("integration-citations")


def test_live_conversation_cleanup() -> None:
    conversation_id = "integration-cleanup"
    _post("/chat", {"conversation_id": conversation_id, "query": "DNA là gì?"})
    cleared = httpx.delete(
        f"{BASE_URL}/conversations/{conversation_id}",
        headers=AUTH_HEADERS,
        verify=VERIFY,
        timeout=10,
    )
    cleared.raise_for_status()
    assert cleared.json()["deleted_turns"] >= 1
