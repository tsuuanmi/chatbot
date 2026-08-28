# `src/domain/classifier.py`

## Purpose

Classifies Vietnamese queries into strict forensic-genetics routing decisions using embedding similarity to reviewed exemplars.

## Responsibilities

- Cache embeddings for in-domain, out-of-domain, clarification, and high-risk exemplar sets.
- Warm the classifier and report readiness.
- Score query embeddings by cosine similarity, confidence threshold, and winning margin.
- Apply configured-figure, prior-context, image-ambiguity, and high-risk routing rules.
- Convert embedding dependency failures into `DomainClassifierError`.

## Non-responsibilities

No answer generation, retrieval, persistence, figure loading, authentication, or legal/scientific conclusion generation.

## Key types and functions

- `_Prototype`: immutable label/vector pair used internally.
- `DomainClassifier.__init__()`: accepts an embedding provider and three routing thresholds.
- `is_ready`: true only after both standard and risk vectors are cached.
- `warmup()`: loads all exemplar vectors.
- `classify()`: returns a `DomainDecision` for a query and optional context flags.
- `_load_vectors()`: performs lock-protected, one-time batch embedding.
- `_cosine()`: computes cosine similarity and returns `0.0` for a zero norm.

## Invariants and errors

- Configured figures bypass embedding and return an in-domain, standard-risk decision at confidence `1.0`.
- Low confidence or insufficient winning margin becomes `CLARIFY`; an ambiguous image also becomes `CLARIFY` unless already in-domain.
- A clarification-class follow-up becomes in-domain when prior context is in-domain.
- A high-risk match forces `IN_DOMAIN` with `CASE_SPECIFIC_CONCLUSION` while retaining the primary class confidence.
- Vector pairs must have equal lengths because `zip(..., strict=True)` is used.
- Warmup and query-time embedding failures raise `DomainClassifierError`; query-time failures are logged.
- Concurrent first use is serialized by an `asyncio.Lock`.

## Dependencies

- `BaseEmbedding` for single and batch embeddings.
- `src.domain.models` for decisions and enums.
- `DomainClassifierError` for the public dependency-failure boundary.
- `asyncio`, `math`, and Loguru.

## Tests

`tests/test_domain_classifier.py` covers warmup caching, dependency failures, exemplar embedding, in/out-of-domain routing, contextual follow-up, image ambiguity, configured-figure bypass, and threshold behavior. Workflow tests exercise downstream decisions.

## Status

Implemented.
