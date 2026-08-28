"""LangGraph chat preparation nodes."""

import asyncio
from typing import Any

from loguru import logger

from src.common.exact_match import get_prepared_answers
from src.config.settings import get_settings
from src.container import get_container
from src.database.history_service import get_history_service
from src.domain.models import DomainLabel, RiskLevel
from src.llm.client import SYSTEM_PROMPT
from src.models.state import AgentState
from src.workflow.routing import resolve_figure_id


async def find_prepared_answer(state: AgentState) -> dict[str, Any]:
    """Return an authoritative exact-match answer before any other work."""
    answer = get_prepared_answers().find(state["query"])
    if answer is None:
        return {"prepared_answer": None}

    if not answer.figure_id:
        logger.info("[prepared_answer] matched question {}", answer.number)
        return {"prepared_answer": answer.answer}

    description = await asyncio.to_thread(
        get_container().figure_descriptions.get, answer.figure_id
    )
    if description is None:
        raise RuntimeError(
            f"Figure '{answer.figure_id}' has not been indexed; "
            "rebuild the knowledge database"
        )
    logger.info("[prepared_answer] matched question {} with figure", answer.number)
    return {
        "prepared_answer": f"{answer.answer}\n\n{description.description}",
        "figure_id": answer.figure_id,
        "figure_description": description.description,
    }


async def resolve_figure_description(state: AgentState) -> dict[str, Any]:
    """Resolve configured figures to their required precomputed descriptions."""
    if state.get("image"):
        return {"figure_description": None}

    figure_id = resolve_figure_id(state["query"], state.get("figure_id"))
    if figure_id is None:
        return {"figure_description": None}

    description = await asyncio.to_thread(
        get_container().figure_descriptions.get, figure_id
    )
    if description is None:
        raise RuntimeError(
            f"Figure '{figure_id}' has not been indexed; rebuild the knowledge database"
        )

    logger.info("[figure_description] resolved {}", figure_id)
    return {
        "figure_id": figure_id,
        "figure_description": description.description,
    }


async def load_domain_context(state: AgentState) -> dict[str, Any]:
    """Load one persisted decision without loading full conversation history."""
    label = await get_history_service().get_latest_domain_label(
        state["conversation_id"], owner_id=state["owner_id"]
    )
    return {"prior_in_domain": label is DomainLabel.IN_DOMAIN}


async def classify_domain(state: AgentState) -> dict[str, Any]:
    """Classify scope with the lightweight semantic model."""
    decision = await get_container().domain_classifier.classify(
        state["query"],
        configured_figure=bool(state.get("figure_description")),
        has_image=bool(state.get("image")),
        prior_in_domain=state.get("prior_in_domain", False),
    )
    logger.info(
        "[domain] label={} risk={} reason={} confidence={:.3f}",
        decision.label,
        decision.risk,
        decision.reason,
        decision.confidence,
    )
    return {"domain_decision": decision}


async def load_conversation_history(state: AgentState) -> dict[str, Any]:
    history = await get_history_service().get_history(
        state["conversation_id"],
        limit=get_settings().history_turn_limit,
        owner_id=state["owner_id"],
    )
    logger.info("[history] loaded {} messages", len(history))
    return {"conversation_history": history}


async def retrieve_knowledge(state: AgentState) -> dict[str, Any]:
    """Retrieve approved relevant evidence for every accepted substantive query."""
    evidence = await get_container().knowledge_retriever.retrieve(state["query"])
    return {"evidence": evidence}


async def aggregate_context(state: AgentState) -> dict[str, Any]:
    """Build one evidence-aware LLM prompt from history and approved context."""
    system_parts = [SYSTEM_PROMPT]
    decision = state.get("domain_decision")
    evidence = state.get("evidence", [])

    authoritative_evidence = any(
        item.metadata.get("topic") != "figure_faq" for item in evidence
    )
    if decision and decision.risk is RiskLevel.HIGH_RISK:
        system_parts.append(
            "Đây là yêu cầu rủi ro cao. Không đưa ra kết luận nhận dạng, huyết thống, "
            "pháp lý hoặc kết luận vụ việc chính thức. Chỉ nêu điều được chứng cứ đã "
            "phê duyệt hỗ trợ, điều chưa thể kết luận và dữ liệu/SOP cần bổ sung."
        )
    if not evidence or (
        decision and decision.risk is RiskLevel.HIGH_RISK and not authoritative_evidence
    ):
        system_parts.append(
            "Cơ sở tri thức đã phê duyệt không có chứng cứ đủ liên quan. Với câu hỏi "
            "rủi ro cao, phải từ chối kết luận. Với câu hỏi kiến thức thông thường, có "
            "thể giải thích thận trọng từ kiến thức nền và nói rõ chưa có nguồn nội bộ."
        )

    figure_description = state.get("figure_description")
    if figure_description:
        system_parts.append(
            "Mô tả đã tính trước của hình được cấu hình:\n" + figure_description
        )

    if evidence:
        context = "\n\n".join(
            f"[{item.id}] {item.content}\n"
            f"Nguồn: {item.source.title}; phiên bản: {item.source.version}; "
            f"mục/trang: {item.source.page_or_section}"
            for item in evidence
        )
        system_parts.append(
            "Chứng cứ đã phê duyệt liên quan:\n"
            f"{context}\n\n"
            "Mọi khẳng định dựa trên chứng cứ phải trích dẫn đúng [ID]. Không dùng ID "
            "không có trong danh sách."
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        *state.get("conversation_history", []),
    ]
    raw_image = state.get("image")
    if raw_image:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": state["query"]},
                    _image_block(raw_image),
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": state["query"]})

    logger.info(
        "[context] {} messages, evidence={}, image={}",
        len(messages),
        len(evidence),
        bool(raw_image),
    )
    return {"aggregated_context": messages}


def accepted_decision(state: AgentState) -> tuple[DomainLabel, RiskLevel]:
    decision = state.get("domain_decision")
    if decision is None:
        return DomainLabel.IN_DOMAIN, RiskLevel.STANDARD
    return decision.label, decision.risk


def _image_block(image: str) -> dict[str, Any]:
    url = image if image.startswith("data:image/") else f"data:image/png;base64,{image}"
    return {"type": "image_url", "image_url": {"url": url}}
