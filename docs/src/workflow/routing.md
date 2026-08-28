# `src/workflow/routing.py`

## Purpose

Provides deterministic routing helpers that do not perform semantic domain classification.

## Responsibilities

- Resolve a configured figure identifier from an explicit argument or supported identifier embedded in a query.
- Detect direct figure description/analysis requests in Vietnamese and English.
- Distinguish direct analysis requests from specific why, count, or comparison questions.
- Convert nullable domain decisions into out-of-domain and clarification route predicates.

## Non-responsibilities

No figure loading, model inference, domain classification, graph construction, state mutation, or answer generation.

## Key types and functions

- `_FIGURE_ID_PATTERN`: case-insensitive pattern for supported prefixes (`heatmap`, `bar`, `pie`, `scatter`, `ridge`, `network`, `tree`, `venn`, `cloud`, `admixture`, and `semipie`) followed by digits.
- `resolve_figure_id(query, figure_id=None) -> str | None`: returns a truthy explicit ID unchanged; otherwise returns the first embedded supported ID in lowercase.
- `is_direct_figure_request(query) -> bool`: recognizes analysis verbs while excluding specific-question phrases.
- `is_out_of_domain(decision) -> bool`: checks for `DomainLabel.OUT_OF_DOMAIN`.
- `needs_clarification(decision) -> bool`: checks for `DomainLabel.CLARIFY`.

## Invariants and errors

- Embedded identifiers must have non-word boundaries and a numeric suffix.
- Explicit identifiers are trusted by this helper and are neither normalized nor pattern-validated.
- A direct figure request requires an analysis phrase and no recognized specific-question phrase.
- Nullable decisions produce `False` for both domain predicates.
- Regular-expression matching is deterministic and raises no expected module-specific errors.

## Dependencies

- Python `re` for identifier and intent matching.
- `src.domain.models.DomainDecision` and `DomainLabel` for route predicates.

## Tests

`tests/test_workflow.py::test_direct_figure_request_uses_precomputed_answer` covers the direct-figure route through the compiled graph. Other helper branches are exercised indirectly by workflow and answer tests; there are no dedicated routing unit tests.

## Status

Implemented.
