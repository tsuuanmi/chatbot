"""Authoritative evidence-aware chat workflow."""

from collections.abc import AsyncGenerator

from langgraph.graph import END, START, StateGraph
from loguru import logger

from src.domain.models import DomainLabel, RiskLevel
from src.knowledge.citations import citation_ids, sanitize_citations
from src.llm.client import get_llm_client
from src.models.state import AgentState, ConversationStatus, ResponseSource
from src.workflow.edges import domain_route, figure_route, prepared_answer_route
from src.workflow.nodes import (
    aggregate_context,
    classify_domain,
    find_prepared_answer,
    load_conversation_history,
    load_domain_context,
    resolve_figure_description,
    retrieve_knowledge,
)

OUT_OF_DOMAIN_MESSAGE = (
    "Xin lỗi, câu hỏi này nằm ngoài phạm vi giám định ADN và di truyền pháp y. "
    "Vui lòng đặt câu hỏi liên quan trực tiếp đến ADN, STR, mtDNA, di truyền quần thể, "
    "xét nghiệm hoặc diễn giải dữ liệu di truyền pháp y."
)
CLARIFICATION_MESSAGE = (
    "Vui lòng bổ sung ngữ cảnh để xác định câu hỏi có thuộc phạm vi giám định ADN và "
    "di truyền pháp y hay không, chẳng hạn loại mẫu, kết quả, hình ảnh hoặc nội dung "
    "chuyên môn cần phân tích."
)
HIGH_RISK_NO_EVIDENCE_MESSAGE = (
    "Cơ sở tri thức đã phê duyệt hiện không có đủ thông tin để hỗ trợ kết luận cho yêu "
    "cầu này. Tôi không thể đưa ra kết luận nhận dạng, huyết thống, pháp lý hoặc kết "
    "luận vụ việc chính thức. Vui lòng đối chiếu dữ liệu đã thẩm định, SOP hiện hành "
    "và chuyên gia giám định có thẩm quyền."
)


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("find_prepared_answer", find_prepared_answer)
    graph.add_node("resolve_figure_description", resolve_figure_description)
    graph.add_node("load_domain_context", load_domain_context)
    graph.add_node("classify_domain", classify_domain)
    graph.add_node("load_history", load_conversation_history)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("aggregate_context", aggregate_context)

    graph.add_edge(START, "find_prepared_answer")
    graph.add_conditional_edges(
        "find_prepared_answer",
        prepared_answer_route,
        {"prepared": END, "figure": "resolve_figure_description"},
    )
    graph.add_conditional_edges(
        "resolve_figure_description",
        figure_route,
        {"prepared": END, "classify": "load_domain_context"},
    )
    graph.add_edge("load_domain_context", "classify_domain")
    graph.add_conditional_edges(
        "classify_domain",
        domain_route,
        {"reject": END, "clarify": END, "continue": "load_history"},
    )
    graph.add_edge("load_history", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "aggregate_context")
    graph.add_edge("aggregate_context", END)
    return graph


_workflow = None


def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = build_graph().compile()
        logger.info("Chat preparation workflow compiled")
    return _workflow


async def prepare_workflow(
    conversation_id: str,
    query: str,
    figure_id: str | None = None,
    image: str | None = None,
    *,
    owner_id: str = "local-development",
) -> AgentState:
    return await get_workflow().ainvoke(
        _initial_state(owner_id, conversation_id, query, figure_id, image)
    )


async def run_workflow(
    conversation_id: str,
    query: str,
    figure_id: str | None = None,
    image: str | None = None,
    *,
    owner_id: str = "local-development",
) -> AgentState:
    state = await prepare_workflow(
        conversation_id, query, figure_id, image, owner_id=owner_id
    )
    direct_response = _direct_response(state)
    if direct_response:
        answer, source, status = direct_response
    else:
        answer = await get_llm_client().chat(messages=state["aggregated_context"])
        answer = sanitize_citations(answer, state["evidence"])
        state["used_citation_ids"] = sorted(citation_ids(answer))
        source, status = "generated", "active"

    return {
        **state,
        "final_answer": answer,
        "response_source": source,
        "conversation_status": status,
    }


async def stream_workflow(
    conversation_id: str,
    query: str,
    figure_id: str | None = None,
    image: str | None = None,
    *,
    owner_id: str = "local-development",
) -> tuple[AgentState, AsyncGenerator[str, None]]:
    state = await prepare_workflow(
        conversation_id, query, figure_id, image, owner_id=owner_id
    )
    direct_response = _direct_response(state)
    if direct_response:
        answer, source, status = direct_response
        state["final_answer"] = answer
        state["response_source"] = source
        state["conversation_status"] = status
        return state, _single_chunk(answer)

    state["response_source"] = "generated"
    allowed_citations = {item.id for item in state["evidence"]}
    return state, get_llm_client().stream_chat(
        messages=state["aggregated_context"],
        allowed_citations=allowed_citations,
    )


def _direct_response(
    state: AgentState,
) -> tuple[str, ResponseSource, ConversationStatus] | None:
    prepared_answer = state.get("prepared_answer")
    if prepared_answer:
        return prepared_answer, "prepared_answer", "active"
    figure_description = state.get("figure_description")
    if figure_description and figure_route(state) == "prepared":
        return figure_description, "figure_prepared", "active"

    decision = state.get("domain_decision")
    if decision and decision.label is DomainLabel.OUT_OF_DOMAIN:
        return OUT_OF_DOMAIN_MESSAGE, "out_of_domain", "ended"
    if decision and decision.label is DomainLabel.CLARIFY:
        return CLARIFICATION_MESSAGE, "clarification", "active"
    if (
        decision
        and decision.risk is RiskLevel.HIGH_RISK
        and not _authoritative_evidence(state)
    ):
        return HIGH_RISK_NO_EVIDENCE_MESSAGE, "generated", "active"
    return None


def _authoritative_evidence(state: AgentState) -> bool:
    return any(
        item.metadata.get("topic") != "figure_faq" for item in state.get("evidence", [])
    )


async def _single_chunk(content: str) -> AsyncGenerator[str, None]:
    yield content


def _initial_state(
    owner_id: str,
    conversation_id: str,
    query: str,
    figure_id: str | None,
    image: str | None,
) -> AgentState:
    return {
        "owner_id": owner_id,
        "conversation_id": conversation_id,
        "query": query,
        "figure_id": figure_id,
        "image": image,
        "prior_in_domain": False,
        "domain_decision": None,
        "conversation_history": [],
        "figure_description": None,
        "evidence": [],
        "used_citation_ids": [],
        "prepared_answer": None,
        "aggregated_context": [],
        "final_answer": "",
        "response_source": None,
        "conversation_status": "active",
    }
