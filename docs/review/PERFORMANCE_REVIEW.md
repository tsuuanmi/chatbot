# Performance & Correctness Review

Date: 2026-08-12
Status: **Reviewed findings resolved and re-verified, including figure precomputation.**
Scope: Historical CPU benchmark and selectable CPU/CUDA deployment behavior.

## 1. Review Outcome

The review originally found two correctness defects:

1. neutral multi-turn follow-ups were rejected as out-of-domain;
2. the ChromaDB collection was empty because the project indexer only considered
   PDFs while the packaged knowledge source is TSV.

Both findings are resolved. The final implementation was rebuilt, indexed, and
exercised through unit, live correctness, and live performance suites. Current
runtime behavior is documented in [`../architecture.md`](../architecture.md).

## 2. Resolved Correctness Findings

### 2.1 Multi-turn domain context — resolved

Final behavior:

```text
turn 1: "DNA là gì?"        → answered
turn 2: "Cấu trúc của nó?"  → generated, active
turn 3: "Cho ví dụ?"         → generated, active
```

The implementation does not move full prompt-history loading ahead of domain
classification. Instead, a dedicated `load_domain_context` node performs a
bounded user-query-only lookup for recognized contextual follow-ups. It finds a
contiguous in-domain topic anchor while stopping at an intervening unrelated
query. This fixes multi-turn conversations without turning old history into a
broad domain whitelist.

Out-of-domain first requests still return `out_of_domain`, `ended`, without full
history loading, retrieval, or Gemma inference.

### 2.2 Empty RAG collection — resolved

Root cause was confirmed: `data/documents/` contains the packaged
`knowledge_base.tsv`, while the former indexer only matched `*.pdf`.

Final behavior:

- one shared typed TSV parser serves prepared answers and RAG indexing;
- the project indexer ingests the TSV plus optional PDFs;
- vector IDs are deterministic (`knowledge:<entry-number>`);
- each source is replaced before insertion, preventing duplicate and stale data;
- the current TSV produces **105 ChromaDB entries**;
- live RAG requests return grounded content with source citations such as
  `[knowledge:25]` and `[knowledge:30]`.

## 3. Latest Live Performance Results

### Historical verified results

The measurements below were captured on the earlier CPU-only stack. They remain a
correctness baseline, not a performance claim for the current selectable CPU/CUDA
profiles. The GTX 1660 Super target still requires final GPU measurement.

| Case | Wall time | Result |
|---|---:|---|
| text-only | sub-second for short answers; answer-length dependent | generated naturally |
| configured figure `bar3` | **~7–9 ms** | `figure_prepared`; no runtime image/model work |
| configured figure `heatmap1` | **~7–8 ms** | `figure_prepared`; no runtime image/model work |
| four-figure stream cycle | **~7–11 ms each** | one direct streamed chunk |
| grounded STR query | **~2.7 s** | grounded answer with `[knowledge:25]` |
| grounded mtDNA stream | **~1.9 s** | grounded answer with `[knowledge:30]` |
| memory over 10 calls | **+0.0 MB** | stable |

Configured figures are now generated once during indexing and stored in the
isolated `chatbot_figures` collection. The current collection contains 21 records;
a second indexing run regenerates zero unchanged figures. Arbitrary uploaded images
remain the runtime multimodal path.

The earlier ~0.45 s RAG reading reflected a very short response generated from an
empty collection; it was not a meaningful grounded-RAG baseline. Current readings
include retrieval and substantive generation, so latency varies with answer depth.

### Memory and resources

- Chatbot RSS during benchmark: 156.8 MB (container usage: 125.8 MiB)
- Memory over 10 calls: **+0.0 MB — stable**
- llama-server: approximately 6.8 GiB resident
- CPU: 16 logical / 8 physical
- GPU device requests: none

## 4. Is Performance Fast Enough?

**Historical CPU correctness was acceptable. Each CPU or CUDA target profile must be
accepted on representative deployment hardware before release.**

- Text chat is interactive; latency grows with the newly comprehensive answer style.
- Grounded RAG remains acceptable for CPU retrieval plus generation.
- Multi-turn follow-ups are real generated answers rather than fast canned rejection.
- Configured-figure latency is no longer a bottleneck after precomputation.
- Arbitrary uploaded images still require runtime multimodal inference.
- Memory is stable with no observed leak.

## 5. Recommended Next Optimization

Do not optimize solely for the smallest wall time. For a Ministry of Public Security
forensic-genetics assistant, prioritize:

1. lightweight semantic domain classification with measured CPU latency;
2. approved-source RAG for substantive accepted questions;
3. evidence sufficiency and high-risk abstention;
4. retrieval/citation quality evaluation;
5. context and generation tuning only after reliability targets pass.

See `DOMAIN_BEHAVIOR_REVIEW.md` and `KNOWLEDGE_RAG_REVIEW.md`.

## 6. Verification Summary

| Gate | Result |
|---|---|
| Unit suite | 53 passed after manifest governance coverage |
| Live correctness suite | 16 passed |
| Live performance suite | 11 passed |
| Ruff | passed |
| mypy | passed |
| compileall | passed |
| Docker build | passed |
| Compose validation | passed |
| Knowledge collection | 105 entries |
| Figure collection | 21 entries; unchanged re-index generated 0 |
| Multi-turn correctness | resolved |
| RAG grounding | resolved |
