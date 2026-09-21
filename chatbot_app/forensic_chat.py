"""Policy-controlled forensic chatbot orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
import os
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from haystack import Pipeline
from hayhooks import async_streaming_generator
from haystack.components.generators.chat import (
    OpenAIChatGenerator,
)
from haystack.dataclasses import (
    ChatMessage,
    ImageContent,
)
from haystack.utils import Secret

from chatbot_app.auth import (
    current_identity,
)
from chatbot_app.capacity import (
    GenerationAdmissionController,
)
from chatbot_app.citations import (
    CitationStreamFilter,
    citation_ids,
    citation_token,
    sanitize_citations,
)
from chatbot_app.conversation import (
    ConversationLockRegistry,
    HistoryContextBuilder,
    bounded_env_int,
)
from chatbot_app.domain import (
    get_domain_classifier,
)
from chatbot_app.evidence import (
    EvidenceItem,
    get_evidence_policy,
)
from chatbot_app.history import (
    get_conversation_repository,
)
from chatbot_app.figure_cache import (
    FigureDescription,
    get_figure_repository,
)
from chatbot_app.figure_routing import (
    is_direct_figure_request,
)
from chatbot_app.media import (
    ImageInput,
    validate_media_input,
)
from chatbot_app.policy import (
    DomainDecision,
    get_domain_policy,
)
from chatbot_app.prepared import (
    PreparedAnswer,
    get_prepared_answers,
)
from chatbot_app.retrieval import (
    get_hybrid_retriever,
)


BASE_SYSTEM_PROMPT = """Bạn là trợ lý AI chuyên về giám định ADN và di truyền pháp y.

Trả lời cùng ngôn ngữ với người dùng.
Trả lời rõ ràng, thận trọng và chính xác.
Không bịa dữ liệu, ngưỡng, SOP, nguồn hoặc kết quả xét nghiệm.
Không suy diễn kết luận nhận dạng, huyết thống hoặc pháp lý từ dữ liệu không được cung cấp.
"""


STANDARD_EVIDENCE_PROMPT = """Các tài liệu bên dưới là nội dung nội bộ đã được phê duyệt để hỗ trợ giải thích, nhưng không mặc nhiên là chứng cứ có thẩm quyền cho kết luận vụ việc.

Chỉ sử dụng chúng khi thực sự liên quan.
Mỗi khẳng định dựa trên tài liệu phải dùng đúng citation dạng [cite:ID].
Không tạo citation ngoài danh sách được cung cấp.
"""


NO_INTERNAL_EVIDENCE_PROMPT = """Không có tài liệu nội bộ phù hợp được chọn cho câu hỏi này.

Bạn có thể giải thích kiến thức nền một cách thận trọng, nhưng không được giả vờ rằng câu trả lời được hỗ trợ bởi nguồn nội bộ và không được tạo citation.
"""


CONVERSATION_HISTORY_PROMPT = """Lịch sử hội thoại bên dưới chỉ được dùng để hiểu tham chiếu và ngữ cảnh hội thoại.

Không coi lịch sử hội thoại là chứng cứ, nguồn chuyên môn hoặc dữ liệu đã được xác minh.
Không tái sử dụng citation từ câu trả lời trước.
Yêu cầu hiện tại, chính sách rủi ro hiện tại và tài liệu truy xuất mới luôn có ưu tiên cao hơn lịch sử.
"""


CONFIGURED_FIGURE_PROMPT = """Thông tin hình được cấu hình bên dưới là mô tả đã được tính trước từ một hình thuộc inventory của hệ thống.

Dùng mô tả này làm ngữ cảnh để trả lời câu hỏi hiện tại.
Không coi mô tả hình là chứng cứ có thẩm quyền.
Không suy diễn dữ liệu không có trong mô tả.
"""

RAW_IMAGE_PROMPT = """Một hình ảnh do người dùng cung cấp được đính kèm trực tiếp trong message hiện tại.

Hãy quan sát trực tiếp nội dung hình khi câu hỏi yêu cầu phân tích hình ảnh.
Không được nói rằng người dùng chưa cung cấp hình nếu image content hiện diện.
Chỉ mô tả hoặc suy luận từ những gì thực sự nhìn thấy trong hình.
Hình do người dùng cung cấp là ngữ cảnh của request, không phải chứng cứ có thẩm quyền và không được dùng để bỏ qua chính sách domain hoặc risk.
"""

HIGH_RISK_PROMPT = """Đây là yêu cầu rủi ro cao.

Không được đưa ra kết luận cuối cùng về danh tính, quan hệ huyết thống, nghi phạm, giá trị pháp lý, SOP bắt buộc hoặc kết luận vụ việc.

Chỉ được mô tả điều mà chứng cứ có thẩm quyền hỗ trợ, giới hạn của chứng cứ và dữ liệu/SOP cần bổ sung.
Mọi khẳng định dựa trên chứng cứ phải có citation hợp lệ.
"""


OUT_OF_DOMAIN_RESPONSE = (
    "Phạm vi hiện tại của trợ lý chỉ bao gồm giám định ADN "
    "và di truyền pháp y. Tôi không xử lý yêu cầu này trong "
    "pipeline chuyên môn hiện tại."
)


CLARIFICATION_RESPONSE = (
    "Bạn vui lòng cung cấp thêm ngữ cảnh hoặc dữ liệu cụ thể "
    "cần phân tích để tôi có thể xác định đúng yêu cầu trong "
    "phạm vi giám định ADN và di truyền pháp y."
)


HIGH_RISK_LIMITATION_RESPONSE = (
    "Tôi không thể đưa ra kết luận cuối cùng cho yêu cầu này. "
    "Kho tri thức hiện tại chưa có nguồn chuyên môn được cấu "
    "hình là chứng cứ có thẩm quyền cho loại kết luận rủi ro "
    "cao này. Cần sử dụng dữ liệu vụ việc, SOP và nguồn chuyên "
    "môn đã được phê duyệt, cùng đánh giá của người có thẩm quyền."
)


class ForensicChatService:
    """Orchestrate policy, exact answers, retrieval and generation."""

    def __init__(self) -> None:
        self.classifier = get_domain_classifier()
        self.domain_policy = get_domain_policy()
        self.prepared = get_prepared_answers()
        self.retriever = get_hybrid_retriever()
        self.evidence_policy = (
            get_evidence_policy()
        )

        self.history = get_conversation_repository()
        self.figures = get_figure_repository()

        self.history_turn_limit = bounded_env_int(
            "HISTORY_TURN_LIMIT",
            default=6,
            minimum=1,
            maximum=20,
        )

        self.history_char_limit = bounded_env_int(
            "HISTORY_CHAR_LIMIT",
            default=8000,
            minimum=1000,
            maximum=24000,
        )

        self.message_max_chars = bounded_env_int(
            "CHAT_MESSAGE_MAX_CHARS",
            default=8000,
            minimum=256,
            maximum=24000,
        )

        self.generation_max_output_tokens = bounded_env_int(
            "LLAMA_MAX_OUTPUT_TOKENS",
            default=2048,
            minimum=128,
            maximum=4096,
        )

        self.generation_queue_timeout_seconds = bounded_env_int(
            "CHAT_GENERATION_QUEUE_TIMEOUT_SECONDS",
            default=5,
            minimum=1,
            maximum=60,
        )

        self.generation_capacity = GenerationAdmissionController(
            limit=1,
            queue_timeout_seconds=(
                self.generation_queue_timeout_seconds
            ),
        )

        self.history_context = HistoryContextBuilder(
            max_turns=self.history_turn_limit,
            max_chars=self.history_char_limit,
        )

        self._conversation_locks = (
            ConversationLockRegistry()
        )

        api_key_path = Path(
            os.environ["LLAMA_API_KEY_FILE"]
        )

        api_key = api_key_path.read_text(
            encoding="utf-8"
        ).strip()

        if not api_key:
            raise RuntimeError(
                "llama.cpp API key file is empty"
            )

        generator = OpenAIChatGenerator(
            api_key=Secret.from_token(
                api_key
            ),
            api_base_url=os.environ[
                "LLAMA_BASE_URL"
            ],
            model=os.environ[
                "LLAMA_MODEL_ALIAS"
            ],
            generation_kwargs={
                "temperature": 0.2,
                "max_tokens": self.generation_max_output_tokens,
            },
            timeout=600.0,
            max_retries=0,
        )

        self.generation = Pipeline()

        self.generation.add_component(
            "llm",
            generator,
        )

    async def answer(
        self,
        message: str,
        conversation_id: str | None = None,
        figure_id: str | None = None,
        image: str | None = None,
        *,
        streaming_callback: (
            Callable[[str], Awaitable[None]]
            | None
        ) = None,
    ) -> dict[str, object]:
        query = message.strip()

        if not query:
            raise ValueError(
                "message must not be empty"
            )

        if len(query) > self.message_max_chars:
            raise ValueError(
                "message exceeds configured maximum length"
            )
        normalized_figure_id, image_input = (
            validate_media_input(
                figure_id=figure_id,
                image=image,
            )
        )

        figure = None

        if normalized_figure_id is not None:
            figure = await self.figures.get(
                normalized_figure_id
            )

            if figure is None:
                raise ValueError(
                    "configured figure was not found"
                )

        if conversation_id is None:
            return await self._answer_core(
                query,
                history=[],
                figure=figure,
                image=image_input,
                streaming_callback=streaming_callback,
            )

        parsed_id = self._parse_conversation_id(
            conversation_id
        )

        owner_id = current_identity().owner_id

        async with self._conversation_locks.hold(
            parsed_id
        ):
            # Claim ownership before expensive work.
            await self.history.ensure_conversation(
                parsed_id,
                owner_id=owner_id,
            )

            history = await self.history.get_turns(
                parsed_id,
                owner_id=owner_id,
                limit=self.history_turn_limit,
            )

            response = await self._answer_core(
                query,
                history=history,
                figure=figure,
                image=image_input,
                streaming_callback=streaming_callback,
            )

            decision = response.get(
                "decision"
            )

            if not isinstance(
                decision,
                dict,
            ):
                raise RuntimeError(
                    "Chat response has no decision metadata"
                )

            saved = await self.history.append_turn(
                parsed_id,
                owner_id=owner_id,
                query=query,
                answer=str(
                    response["answer"]
                ),
                domain=str(
                    decision["domain"]
                ),
                risk=str(
                    decision["risk"]
                ),
                source=str(
                    response["source"]
                ),
            )

        persisted = dict(response)

        persisted["conversation_id"] = str(
            parsed_id
        )
        persisted["turn"] = saved.turn
        persisted["history_turns_loaded"] = len(
            history
        )

        return persisted

    async def stream_answer(
        self,
        message: str,
        conversation_id: str | None = None,
        figure_id: str | None = None,
        image: str | None = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        queue: asyncio.Queue[
            tuple[str, object]
        ] = asyncio.Queue()

        async def emit(
            content: str,
        ) -> None:
            if content:
                await queue.put(
                    ("chunk", content)
                )

        async def run() -> None:
            try:
                result = await self.answer(
                    message,
                    conversation_id,
                    figure_id=figure_id,
                    image=image,
                    streaming_callback=emit,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                await queue.put(
                    ("error", error)
                )
            else:
                await queue.put(
                    ("done", result)
                )

        task = asyncio.create_task(
            run()
        )

        emitted = False

        try:
            yield {
                "type": "start",
                "conversation_id": conversation_id,
            }

            while True:
                kind, payload = await queue.get()

                if kind == "chunk":
                    emitted = True
                    yield {
                        "type": "chunk",
                        "content": str(payload),
                    }
                    continue

                if kind == "error":
                    if isinstance(
                        payload,
                        BaseException,
                    ):
                        raise payload

                    raise RuntimeError(
                        "stream failed"
                    )

                if kind != "done":
                    raise RuntimeError(
                        "unknown stream event"
                    )

                if not isinstance(
                    payload,
                    dict,
                ):
                    raise RuntimeError(
                        "invalid final stream result"
                    )

                result = payload

                if (
                    not emitted
                    and result.get("answer")
                ):
                    yield {
                        "type": "chunk",
                        "content": str(
                            result["answer"]
                        ),
                    }

                end = {
                    "type": "end",
                    "source": result.get(
                        "source"
                    ),
                    "decision": result.get(
                        "decision"
                    ),
                    "evidence_status": result.get(
                        "evidence_status"
                    ),
                    "citations": result.get(
                        "citations",
                        [],
                    ),
                }

                for key in (
                    "conversation_id",
                    "turn",
                    "history_turns_loaded",
                ):
                    if key in result:
                        end[key] = result[key]

                yield end
                return

        finally:
            if not task.done():
                task.cancel()

                with suppress(
                    asyncio.CancelledError
                ):
                    await task

    async def _answer_core(
        self,
        query: str,
        *,
        history: list,
        figure: FigureDescription | None,
        image: ImageInput | None,
        streaming_callback: (
            Callable[[str], Awaitable[None]]
            | None
        ) = None,
    ) -> dict[str, object]:
        scores = await asyncio.to_thread(
            self.classifier.classify,
            query,
        )

        decision = self.domain_policy.decide(
            query,
            scores,
        )
        # A configured figure is known project context.
        # It may establish domain, but it must never
        # downgrade a high-risk decision.
        if (
            figure is not None
            and decision.risk == "standard"
        ):
            decision = replace(
                decision,
                domain="in_domain",
                reason="configured_figure",
            )

        retrieval_query = query

        # History may resolve an ambiguous current request, but it may
        # never override a clear out-of-domain decision or downgrade risk.
        if (
            history
            and decision.domain == "clarify"
            and decision.risk == "standard"
        ):
            contextual_query = (
                self.history_context.contextual_query(
                    query,
                    history,
                )
            )

            if contextual_query:
                contextual_scores = await asyncio.to_thread(
                    self.classifier.classify,
                    contextual_query,
                )

                contextual_decision = (
                    self.domain_policy.decide(
                        contextual_query,
                        contextual_scores,
                    )
                )

                if (
                    contextual_decision.risk == "high"
                    or contextual_decision.domain
                    == "in_domain"
                ):
                    decision = replace(
                        contextual_decision,
                        reason=(
                            "contextual_"
                            + contextual_decision.reason
                        ),
                    )

                    retrieval_query = contextual_query

        prepared = self.prepared.find(
            query
        )

        # Risk always wins over exact prepared content.
        if decision.risk == "high":
            return await self._answer_high_risk(
                query,
                decision,
                history=history,
                figure=figure,
                image=image,
                streaming_callback=streaming_callback,
            )

        # Raw uploaded images are request-specific context.
        # Do not let an exact text match silently ignore them.
        if prepared is not None and image is None:
            return self._prepared_response(
                prepared,
                decision,
            )

        if (
            figure is not None
            and is_direct_figure_request(query)
        ):
            return self._figure_response(
                figure,
                decision,
            )

        if decision.domain == "out_of_domain":
            return self._fixed_response(
                answer=OUT_OF_DOMAIN_RESPONSE,
                source="out_of_domain",
                decision=decision,
            )

        if decision.domain == "clarify":
            return self._fixed_response(
                answer=CLARIFICATION_RESPONSE,
                source="clarification",
                decision=decision,
            )

        retrieval = await self.retriever.retrieve(
            retrieval_query
        )

        evidence = self.evidence_policy.select(
            retrieval,
            high_risk=False,
        )

        return await self._generate(
            query,
            decision,
            evidence,
            high_risk=False,
            history=history,
            figure=figure,
            image=image,
            streaming_callback=streaming_callback,
        )

    @staticmethod
    def _parse_conversation_id(
        value: str,
    ) -> UUID:
        """Parse the internal conversation identifier defensively."""

        value = value.strip()

        if not value:
            raise ValueError(
                "conversation_id must not be empty"
            )

        try:
            return UUID(value)
        except ValueError as error:
            raise ValueError(
                "conversation_id must be a valid UUID"
            ) from error

    async def _answer_high_risk(
        self,
        query: str,
        decision: DomainDecision,
        *,
        history: list,
        figure: FigureDescription | None,
        image: ImageInput | None,
        streaming_callback: (
            Callable[[str], Awaitable[None]]
            | None
        ) = None,
    ) -> dict[str, object]:
        # Current corpus intentionally has no authoritative topic.
        if (
            not self.evidence_policy
            .has_authoritative_topics
        ):
            return self._fixed_response(
                answer=HIGH_RISK_LIMITATION_RESPONSE,
                source="evidence_limitation",
                decision=decision,
                evidence_status="insufficient",
            )

        retrieval = await self.retriever.retrieve(
            query
        )

        evidence = self.evidence_policy.select(
            retrieval,
            high_risk=True,
        )

        if not evidence:
            return self._fixed_response(
                answer=HIGH_RISK_LIMITATION_RESPONSE,
                source="evidence_limitation",
                decision=decision,
                evidence_status="insufficient",
            )

        return await self._generate(
            query,
            decision,
            evidence,
            high_risk=True,
            history=history,
            figure=figure,
            image=image,
            streaming_callback=streaming_callback,
        )

    def _prepared_response(
        self,
        prepared: PreparedAnswer,
        decision: DomainDecision,
    ) -> dict[str, object]:
        token = citation_token(
            prepared.citation_id
        )

        return {
            "answer": (
                f"{prepared.answer}\n\n{token}"
            ),
            "source": "prepared_answer",
            "decision": decision.to_dict(),
            "evidence_status": "supporting",
            "citations": [
                prepared.citation()
            ],
        }

    @staticmethod
    def _figure_response(
        figure: FigureDescription,
        decision: DomainDecision,
    ) -> dict[str, object]:
        return {
            "answer": figure.description,
            "source": "figure_prepared",
            "decision": decision.to_dict(),
            "evidence_status": "not_applicable",
            "citations": [],
            "figure_id": figure.figure_id,
        }

    @staticmethod
    def _fixed_response(
        *,
        answer: str,
        source: str,
        decision: DomainDecision,
        evidence_status: str = "not_applicable",
    ) -> dict[str, object]:
        return {
            "answer": answer,
            "source": source,
            "decision": decision.to_dict(),
            "evidence_status": evidence_status,
            "citations": [],
        }

    async def _generate(
        self,
        query: str,
        decision: DomainDecision,
        evidence: list[EvidenceItem],
        *,
        high_risk: bool,
        history: list,
        figure: FigureDescription | None,
        image: ImageInput | None,
        streaming_callback: (
            Callable[[str], Awaitable[None]]
            | None
        ) = None,
    ) -> dict[str, object]:
        system_parts = [
            BASE_SYSTEM_PROMPT,
        ]

        if high_risk:
            system_parts.append(
                HIGH_RISK_PROMPT
            )

        if image is not None:
            system_parts.append(
                RAW_IMAGE_PROMPT
            )

        if evidence:
            system_parts.append(
                STANDARD_EVIDENCE_PROMPT
            )

            system_parts.append(
                self._evidence_context(
                    evidence
                )
            )
        else:
            system_parts.append(
                NO_INTERNAL_EVIDENCE_PROMPT
            )

        if figure is not None:
            system_parts.append(
                CONFIGURED_FIGURE_PROMPT
            )
            system_parts.append(
                "\n".join(
                    (
                        f"figure_id={figure.figure_id}",
                        f"description={figure.description}",
                    )
                )
            )

        history_messages = (
            self.history_context.prompt_messages(
                history
            )
        )

        if history_messages:
            system_parts.append(
                CONVERSATION_HISTORY_PROMPT
            )

        messages = [
            ChatMessage.from_system(
                "\n\n".join(system_parts)
            )
        ]

        for item in history_messages:
            if item.role == "user":
                messages.append(
                    ChatMessage.from_user(
                        item.content
                    )
                )
            else:
                messages.append(
                    ChatMessage.from_assistant(
                        item.content
                    )
                )

        if image is None:
            messages.append(
                ChatMessage.from_user(query)
            )
        else:
            image_content = ImageContent(
                base64_image=image.base64_image,
                mime_type=image.mime_type,
                validation=False,
            )

            messages.append(
                ChatMessage.from_user(
                    content_parts=[
                        query,
                        image_content,
                    ]
                )
            )

        allowed = {
            item.citation_id
            for item in evidence
        }

        async with self.generation_capacity.slot():
            answer = await self._invoke_model(
                messages,
                allowed,
                streaming_callback,
            )
        used = citation_ids(answer)

        citations = [
            item.citation()
            for item in evidence
            if item.citation_id in used
        ]

        return {
            "answer": answer,
            "source": "generated",
            "decision": decision.to_dict(),
            "evidence_status": (
                "authoritative"
                if high_risk
                else (
                    "supporting"
                    if evidence
                    else "insufficient"
                )
            ),
            "citations": citations,
        }

    async def _invoke_model(
        self,
        messages: list[ChatMessage],
        allowed: set[str],
        streaming_callback: (
            Callable[[str], Awaitable[None]]
            | None
        ),
    ) -> str:
        if streaming_callback is None:
            result = await self.generation.run_async(
                {
                    "llm": {
                        "messages": messages,
                    }
                }
            )

            answer = result[
                "llm"
            ]["replies"][0].text

            return sanitize_citations(
                answer,
                allowed,
            )

        citation_filter = CitationStreamFilter(
            allowed
        )

        parts: list[str] = []

        stream = async_streaming_generator(
            pipeline=self.generation,
            pipeline_run_args={
                "llm": {
                    "messages": messages,
                }
            },
            streaming_components=[
                "llm"
            ],
        )

        async for chunk in stream:
            content = getattr(
                chunk,
                "content",
                "",
            )

            if not content:
                continue

            safe = citation_filter.feed(
                content
            )

            if safe:
                parts.append(safe)

                await streaming_callback(
                    safe
                )

        tail = citation_filter.finish()

        if tail:
            parts.append(tail)

            await streaming_callback(
                tail
            )

        return "".join(parts)

    @staticmethod
    def _evidence_context(
        evidence: list[EvidenceItem],
    ) -> str:
        blocks: list[str] = []

        for item in evidence:
            document = item.document
            meta = document.meta
            token = citation_token(
                item.citation_id
            )

            blocks.append(
                "\n".join(
                    (
                        f"{token}",
                        document.content or "",
                        (
                            "Nguồn: "
                            f"{meta.get('source_title') or 'unknown'}"
                        ),
                        (
                            "Phiên bản: "
                            f"{meta.get('source_version') or 'unknown'}"
                        ),
                        (
                            "Mục/trang: "
                            f"{meta.get('source_page_or_section') or 'unknown'}"
                        ),
                    )
                )
            )

        return (
            "Tài liệu nội bộ liên quan:\n\n"
            + "\n\n".join(blocks)
        )


@lru_cache
def get_forensic_chat() -> ForensicChatService:
    return ForensicChatService()
