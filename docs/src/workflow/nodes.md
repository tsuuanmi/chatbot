# `src/workflow/nodes.py`

## Purpose

Implements the asynchronous LangGraph preparation nodes that resolve authoritative answers and figures, classify scope, load conversation context, retrieve evidence, and build the LLM request.

## Responsibilities

- Return approved exact-match answers before other work, including required precomputed figure descriptions.
- Resolve explicit or query-embedded configured figures to indexed descriptions while excluding uploaded-image requests.
- Load the latest persisted domain label to provide prior in-domain context.
- Invoke the semantic domain classifier with figure, image, and prior-conversation signals.
- Load bounded owner-scoped conversation history.
- Retrieve approved evidence for accepted substantive queries.
- Build the system prompt from policy, risk guidance, evidence availability, figure description, and source metadata.
- Append prior history and the current text-only or image-bearing user message.

## Non-responsibilities

No graph construction, route selection, final direct-response selection, language-model invocation, citation output filtering, history writes, figure generation, or evidence indexing.

## Key types and functions

- `find_prepared_answer(state) -> dict[str, Any]`: finds a normalized exact match and optionally combines its answer with an indexed figure description.
- `resolve_figure_description(state) -> dict[str, Any]`: resolves a configured figure unless a raw image was supplied.
- `load_domain_context(state) -> dict[str, Any]`: maps the latest persisted label to `prior_in_domain`.
- `classify_domain(state) -> dict[str, Any]`: invokes and logs the domain decision.
- `load_conversation_history(state) -> dict[str, Any]`: loads owner-scoped history using the configured turn limit.
- `retrieve_knowledge(state) -> dict[str, Any]`: retrieves approved evidence for the current query.
- `aggregate_context(state) -> dict[str, Any]`: creates OpenAI-compatible system, history, and user messages.
- `accepted_decision(state) -> tuple[DomainLabel, RiskLevel]`: returns the decision pair or defaults to in-domain, standard risk when absent.
- `_image_block(image) -> dict[str, Any]`: preserves existing image data URLs or wraps raw base64 as PNG.

## Invariants and errors

- Exact matches without a figure return only `prepared_answer`; matches with a figure require an indexed description and concatenate it after two newlines.
- Uploaded images bypass configured figure-description resolution.
- A referenced configured figure with no indexed description raises `RuntimeError` instructing the operator to rebuild the knowledge database.
- Prior context is true only when the latest persisted label is exactly `IN_DOMAIN`.
- High-risk prompts prohibit official identity, parentage, legal, or case conclusions.
- No-evidence guidance is added when evidence is empty, or when a high-risk query has only `figure_faq` evidence.
- Evidence blocks include IDs and source title, version, and page/section, and instruct the model to cite only listed IDs.
- Conversation history is inserted between the system message and current user message without transformation.
- Any string beginning `data:image/` is accepted as an image URL; all other strings are treated as raw PNG base64 without decoding validation here.
- Missing required state keys and failures from repositories, stores, classifier, retriever, settings, or history service propagate.

## Dependencies

- `src.common.exact_match` for approved prepared answers.
- `src.container` for figure descriptions, domain classification, and knowledge retrieval.
- `src.database.history_service` for persisted labels and conversation history.
- `src.config.settings` for history limits.
- `src.llm.client.SYSTEM_PROMPT` for base model instructions.
- `src.workflow.routing.resolve_figure_id` for configured figure detection.
- `src.domain.models` and `src.models.state` for decisions, risks, and state typing.
- `asyncio.to_thread` for synchronous figure-store access and Loguru for stage logging.

## Tests

`tests/test_workflow.py` exercises prepared-answer nodes through graph patches and directly verifies missing indexed figure descriptions raise `RuntimeError`. Graph tests also cover accepted retrieval sequencing. Prompt aggregation details, owner-scoped history arguments, classification flags, image wrapping, `accepted_decision`, and prepared answers with figures have no dedicated tests.

## Status

Implemented.
