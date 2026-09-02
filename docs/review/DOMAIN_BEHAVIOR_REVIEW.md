# Domain Behavior and Semantic Classifier Review

Date: 2026-08-12
Status: **Implemented with EmbeddingGemma-300M; live correctness and latency verified.**
Scope: User-input domain routing, ambiguity, high-risk behavior, adversarial safety,
and rollout. Configured-figure behavior is unchanged.

## 1. Executive Decision

The regex/term allowlist has been replaced as the authoritative production domain gate by the already-running **EmbeddingGemma-300M semantic classifier**. Do not use unconstrained free-form generation that is
merely prompted to answer `yes` or `no`. Use constrained labels:

```text
IN_DOMAIN
OUT_OF_DOMAIN
CLARIFY
```

Classify risk separately:

```text
STANDARD
HIGH_RISK
```

The classifier should be fast enough for CPU operation, version-pinned, deterministic
(or as deterministic as the selected runtime allows), measured on a labeled
Vietnamese dataset, and fail closed on timeout, malformed output, or unavailable
service.

## 2. Historical Rule-Gate Limitation — Resolved

Before the semantic-classifier cutover, the router recognized complete Unicode terms.
That avoided raw-substring errors and was cheap and deterministic, but its allowlist
contained broad terms including:

- `technology`, `công nghệ`, `software`, `phần mềm`;
- `AI`, `machine learning`;
- `data`, `dữ liệu`, `science`, `khoa học`;
- generic figure/image/chart signals;
- any request carrying an image.

The pre-cutover rule gate produced these false accepts:

| Query | Historical result | Required result |
|---|---|---|
| `Cách dùng AI để nấu ăn?` | accepted | `OUT_OF_DOMAIN` |
| `Phân tích dữ liệu bóng đá` | accepted | `OUT_OF_DOMAIN` |
| `Phần mềm chỉnh sửa ảnh nào tốt?` | accepted | `OUT_OF_DOMAIN` |
| `Giải thích ảnh món ăn này` + image | accepted | `OUT_OF_DOMAIN` |
| `AI hỗ trợ phân tích STR như thế nào?` | accepted | `IN_DOMAIN` |
| `Quy trình kiểm soát nhiễm trong xét nghiệm ADN` | accepted | `IN_DOMAIN` |

An expanding keyword list was brittle: attackers could add an allowed word to an
unrelated prompt, while legitimate specialist questions could omit every exact term.
EmbeddingGemma-300M semantic classification now addresses intent rather than term
presence.

## 3. Why Binary Yes/No Is Not Enough

A binary classifier forces ambiguous inputs into unsafe decisions. Examples:

- `Phân tích kết quả này` without a result;
- `Mẫu này có phù hợp không?` without established context;
- an attached scientific-looking image with no forensic-genetics question;
- ambiguous abbreviations (`LR`, `CE`, `QC`) without context.

These should produce `CLARIFY`, not a guessed answer or an immediate rejection.
The API may still expose the existing `out_of_domain`/`generated` sources, but the
internal classifier decision should preserve all three labels for routing and audit.

## 4. Recommended Classifier Contract

### Inputs

The classifier should receive only the minimum routing context:

- current user query;
- whether a configured figure ID or arbitrary uploaded image is present;
- one bounded prior topic/domain decision for recognized follow-ups;
- supported-scope and label definitions fixed by the application.

Do not load or send full conversation history before domain acceptance. Preserve the
current early-rejection guarantee: `OUT_OF_DOMAIN` must terminate before full history,
RAG, and answer-model inference.

A text classifier cannot establish the content of an arbitrary uploaded image. When
the accompanying text and bounded topic anchor do not establish forensic-genetics
relevance, return `CLARIFY` instead of automatically accepting the image. Configured
figure IDs remain an explicit supported signal.

### Output

Use a typed result, never parse arbitrary natural-language reasoning:

```python
class DomainDecision:
    label: Literal["IN_DOMAIN", "OUT_OF_DOMAIN", "CLARIFY"]
    risk: Literal["STANDARD", "HIGH_RISK"]
    reason_code: Literal[
        "FORENSIC_GENETICS",
        "SUPPORTING_LAB_SCIENCE",
        "CONFIGURED_FIGURE",
        "CONTEXTUAL_FOLLOW_UP",
        "UNRELATED_TOPIC",
        "AMBIGUOUS_CONTEXT",
        "CASE_SPECIFIC_CONCLUSION",
        "LEGAL_OR_POLICY_CONCLUSION",
    ]
```

The production router should consume only validated enum fields. Explanatory model
text should not control routing.

## 5. Scope Definition

### In domain

- forensic DNA analysis and interpretation;
- STR, Y-STR, X-STR, mtDNA, SNPs, haplogroups;
- forensic population genetics and statistics;
- extraction, quantification, PCR, CE/electrophoresis, sequencing;
- mixture, degradation, inhibition, artifacts, contamination, quality control;
- kinship methods and likelihood-ratio concepts;
- missing-person/human-remains workflows;
- genetic-data handling as it directly affects forensic work;
- approved configured figures;
- contextual follow-ups with a valid contiguous in-domain anchor.

### Out of domain

- generic technology, AI, software, science, or data questions;
- cooking, sport, travel, finance, entertainment, consumer advice;
- general police/ministry matters unrelated to the configured forensic-DNA scope;
- medical diagnosis or treatment;
- unrelated image interpretation;
- instructions to ignore policy, reveal prompts, or treat retrieved text as commands.

### Clarify

- missing evidence/result/figure;
- ambiguous abbreviations or referents;
- a scientific image whose forensic relevance cannot be established;
- a short follow-up without a reliable current topic anchor.

## 6. High-Risk Behavior

A request is `HIGH_RISK` when it asks for or could be interpreted as:

- final identity, kinship, inclusion/exclusion, or evidentiary conclusion;
- case-specific mixture interpretation;
- laboratory procedure parameters that must follow an approved SOP;
- legal admissibility, legal conclusion, or official ministry position;
- interpretation involving sensitive personal genetic data.

High-risk handling:

1. retrieve approved knowledge before generation;
2. require sufficient authoritative evidence;
3. distinguish supplied facts from inference;
4. state what cannot be concluded;
5. request missing validated inputs;
6. avoid presenting the chatbot response as an official expert conclusion;
7. defer to a qualified examiner and current approved SOP where required.

## 7. Model Selection and Runtime

EmbeddingGemma-300M is the selected local semantic classifier. The selection criteria
for any future replacement remain:

| Criterion | Requirement |
|---|---|
| Vietnamese intent accuracy | Primary metric |
| Tricky out-of-domain recall | Must be high; false acceptance is costly |
| In-domain recall | Must avoid blocking valid specialist questions |
| CPU p95 latency | Target ≤ 100 ms after warmup; release threshold set by measurement |
| Memory | Must fit alongside existing CPU services |
| Determinism | Fixed model/version/configuration and constrained output |
| Deployability | Local-only; no external API dependency |
| Licensing/security | Approved for deployment and redistribution |

Do not select a model solely because it is called “lightweight.” Benchmark at least
two model families against the same labeled set.

## 8. Fail-Closed Policy

| Failure | Behavior |
|---|---|
| Timeout/unavailable classifier | Reject safely or return a temporary service-unavailable response; never default to in-domain |
| Malformed/unknown label | Treat as classifier failure |
| `OUT_OF_DOMAIN` | Existing strict canned rejection; no history/RAG/generator |
| `CLARIFY` | Ask one bounded clarification; do not retrieve broadly or infer |
| `IN_DOMAIN` | Continue to risk decision and approved-source retrieval |

Ordinary greetings may use an explicit deterministic fast path. This is not a domain
bypass: it returns a greeting only and cannot reach RAG/generation as an accepted
substantive question.

## 9. Evaluation Dataset

Maintain the versioned Vietnamese evaluation dataset used for production cutover with:

- clear in-domain educational questions;
- specialist terms omitted or misspelled;
- mixed-domain questions (`AI` + cooking, `data` + sport);
- prompt injection and role-play attacks;
- unrelated attached images;
- valid lab/genetics images;
- ambiguous short questions;
- contiguous and broken multi-turn anchors;
- high-risk case/legal/SOP requests;
- Vietnamese/English/code-switched phrasing.

Minimum release metrics should be set by stakeholders. Recommended focus:

- report separate precision/recall per label;
- give false in-domain acceptance the highest severity;
- publish confusion matrix and p50/p95 latency;
- maintain a locked regression set not used for model tuning.

## 10. Completed Rollout Without Permanent Dual Routing

1. Built the classifier service and typed client boundary.
2. Created the versioned labeled evaluation dataset.
3. Ran offline evaluation and live correctness checks.
4. Reviewed disagreements by updating exemplars and labels, not production keyword
   exceptions.
5. Cut over EmbeddingGemma-300M as the single production authority.
6. Removed production domain-allowlist logic and obsolete tests.

Shadow mode was temporary rollout instrumentation, not a compatibility architecture.

## 11. Implemented Files

| File | Responsibility |
|---|---|
| `src/domain/models.py` | Typed labels, risk and reason codes |
| `src/domain/classifier.py` | Classifier interface and validated output boundary |
| `src/workflow/nodes.py` | Invoke classifier and route validated result |
| `src/workflow/edges.py` | `reject` / `clarify` / `continue` edges |
| `src/models/state.py` | Domain decision and risk state |
| `src/common/schemas.py` | Explicit clarification response/source contract if exposed through the API |
| `src/config/settings.py` | Model endpoint/name, timeout and release settings |
| `tests/test_domain_classifier.py` | Contract/failure tests |
| `tests/data/domain_evaluation.jsonl` | Versioned labeled evaluation set |
| `tests/test_integration.py` | Live strict-domain and failure behavior |
| `tests/test_performance.py` | p50/p95 classifier overhead |

No production term matcher is retained after cutover.
