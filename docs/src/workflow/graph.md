# `src/workflow/graph.py`

## Purpose

Defines the authoritative evidence-aware chat preparation graph and resolves prepared, rejected, clarified, guarded high-risk, generated, and streaming responses.

## Responsibilities

- Assemble LangGraph nodes and conditional edges in the required preparation order.
- Stop early for exact prepared answers, direct configured figure descriptions, out-of-domain decisions, and clarification decisions.
- Load history, retrieve evidence, and aggregate model context for accepted substantive queries.
- Compile and cache one process-local workflow.
- Build complete initial state from request and owner inputs.
- Resolve fixed direct responses before invoking the language model.
- Sanitize citations after non-streaming generation and record used citation IDs.
- Restrict streaming citations to retrieved evidence IDs.
- Prevent unsupported high-risk conclusions when no authoritative non-figure evidence exists.

## Non-responsibilities

No exact-match lookup, figure-store access, classification implementation, history persistence, evidence search, prompt assembly details, API serialization, or saving generated conversation turns. Streaming consumers are responsible for collecting chunks and any final bookkeeping not represented here.

## Key types and functions

- `OUT_OF_DOMAIN_MESSAGE`, `CLARIFICATION_MESSAGE`, `HIGH_RISK_NO_EVIDENCE_MESSAGE`: fixed Vietnamese direct responses.
- `build_graph() -> StateGraph`: registers preparation nodes, edges, and terminal branches.
- `get_workflow()`: lazily compiles and caches the graph.
- `prepare_workflow(...) -> AgentState`: invokes the compiled preparation graph with a complete initial state.
- `run_workflow(...) -> AgentState`: returns a direct response or one complete generated answer with sanitized citations and final metadata.
- `stream_workflow(...) -> tuple[AgentState, AsyncGenerator[str, None]]`: returns prepared state plus either a one-chunk direct response or a filtered model stream.
- `_direct_response(state)`: applies direct-response precedence.
- `_authoritative_evidence(state) -> bool`: treats evidence whose `topic` is not `figure_faq` as authoritative.
- `_single_chunk(content)`: adapts fixed text to the streaming interface.
- `_initial_state(...) -> AgentState`: supplies defaults for every declared state key.

## Invariants and errors

- Graph route labels must match the mappings returned by edge selectors.
- Preparation order is exact match, figure resolution, domain context/classification, history, retrieval, then context aggregation.
- Direct-response precedence is prepared answer, direct figure description, out-of-domain, clarification, then unsupported high-risk guard.
- Prepared answers and direct figure descriptions remain active; out-of-domain responses end the conversation; clarification and guarded high-risk responses remain active.
- High-risk evidence is authoritative unless its metadata topic equals `figure_faq`; missing topic therefore counts as authoritative.
- Non-streaming generated answers are citation-sanitized and populate sorted `used_citation_ids`.
- Streaming state is marked `generated` before consumption but this module does not assemble streamed chunks into `final_answer` or populate `used_citation_ids` afterward.
- LangGraph node failures, missing required state keys, LLM errors, and citation helper errors propagate.
- The workflow singleton has no locking around first compilation.

## Dependencies

- LangGraph `StateGraph`, `START`, and `END` for graph execution.
- `src.workflow.nodes` and `src.workflow.edges` for stage implementations and routing.
- `src.models.state` for state and response metadata contracts.
- `src.domain.models` for label and risk decisions.
- `src.knowledge.citations` for citation sanitization and extraction.
- `src.llm.client` for generated completion and streaming.
- Loguru for compilation logging.

## Tests

`tests/test_workflow.py` verifies early prepared-answer termination, rejection before history/retrieval, mandatory retrieval for accepted queries, direct-figure termination, and unindexed-figure errors. `tests/test_answer.py` verifies prepared, generated, rejected, clarification, and streaming response behavior. High-risk no-evidence handling, citation sanitization, initial-state defaults, and singleton compilation have no dedicated tests.

## Status

Implemented.
