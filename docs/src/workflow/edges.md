# `src/workflow/edges.py`

## Purpose

Defines the conditional edge selectors used by the chat preparation graph.

## Responsibilities

- End preparation immediately when an exact prepared answer exists.
- End preparation for a precomputed direct figure description when no uploaded image requires further handling.
- Route domain decisions to rejection, clarification, or continued context preparation.
- Return route labels constrained to the labels registered by `build_graph`.

## Non-responsibilities

No state mutation, figure resolution, semantic classification, graph construction, persistence, retrieval, or answer generation.

## Key types and functions

- `prepared_answer_route(state) -> Literal["prepared", "figure"]`: selects a prepared-answer exit or figure-resolution stage based on truthiness.
- `figure_route(state) -> Literal["prepared", "classify"]`: selects the prepared-figure exit only when a description exists, the query is a direct figure request, and no image was uploaded.
- `domain_route(state) -> Literal["reject", "clarify", "continue"]`: prioritizes out-of-domain rejection, then clarification, and otherwise continues.

## Invariants and errors

- Route labels must remain synchronized with the conditional-edge mappings in `src/workflow/graph.py`.
- Empty prepared answers and figure descriptions are treated as absent.
- `figure_route` indexes `state["query"]`; a malformed runtime dictionary without that required key raises `KeyError`.
- Missing or null domain decisions route to `continue`.

## Dependencies

- `src.models.state.AgentState` for the shared state contract.
- `src.workflow.routing` for direct-figure and domain-decision predicates.
- Python `Literal` for route-label typing.

## Tests

`tests/test_workflow.py` exercises prepared-answer termination, direct-figure termination, out-of-domain termination, and accepted-query continuation through a compiled graph. Clarification routing is exercised by `tests/test_answer.py` after preparation is mocked.

## Status

Implemented.
