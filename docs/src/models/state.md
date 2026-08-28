# `src/models/state.py`

## Purpose

Defines the typed state contract shared by LangGraph chat preparation and answer resolution.

## Responsibilities

- Enumerate every field passed between workflow nodes and final response handling.
- Restrict response provenance to the supported response-source literals.
- Restrict conversation lifecycle state to active or ended.
- Type domain decisions, retrieved evidence, conversation history, aggregated model messages, and figure data.

## Non-responsibilities

No state validation, default construction, persistence, routing, or workflow execution. As a `TypedDict`, `AgentState` supplies static typing but does not enforce fields or values at runtime.

## Key types and functions

- `ResponseSource`: literal response origins: prepared answer, prepared figure, generated answer, out-of-domain rejection, or clarification.
- `ConversationStatus`: literal lifecycle values `active` and `ended`.
- `AgentState`: required-key `TypedDict` containing request identity and input, classification and history, evidence and citations, prepared context, and final response metadata.

## Invariants and errors

- The declared contract requires all `AgentState` keys, although ordinary dictionaries can still violate it at runtime.
- `aggregated_context` permits arbitrary value shapes through `Any` because it is passed to the OpenAI-compatible client.
- `domain_decision`, `figure_description`, `prepared_answer`, and `response_source` are nullable until their workflow stages resolve them.
- The module raises no module-specific errors.

## Dependencies

- `src.domain.models.DomainDecision` for semantic scope and risk decisions.
- `src.knowledge.models.Evidence` for retrieved approved evidence.
- Python `typing` for literals, `TypedDict`, and open context values.

## Tests

`tests/test_workflow.py` constructs complete `AgentState` values and passes them through compiled graph branches. `tests/test_answer.py` exercises response-source and conversation-status outcomes using workflow state dictionaries.

## Status

Implemented.
