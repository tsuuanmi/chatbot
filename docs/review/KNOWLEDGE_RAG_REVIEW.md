# Knowledge and RAG Reliability Review

Date: 2026-08-12
Status: **Core approved retrieval, provenance, citation, and evidence policy implemented; expert corpus expansion remains ongoing.**
Scope: Knowledge content, provenance, retrieval, evidence sufficiency, citations,
answer policy, lifecycle, and testing. Figure precomputation remains unchanged.

## 1. Executive Decision

For substantive in-domain questions, use approved RAG knowledge as the default
evidence source rather than relying primarily on Gemma's internal knowledge.
RAG remains independent from domain classification:

- the semantic classifier decides whether the request is in scope;
- retrieval supplies evidence after acceptance;
- failed/empty retrieval must not silently become a confident unsupported answer;
- ordinary low-risk questions may use carefully qualified model knowledge when the
  corpus lacks evidence;
- high-risk questions require approved evidence or an explicit limitation/abstention.

## 2. Current Corpus Findings

`data/documents/knowledge_base.tsv` currently contains **105 records** grouped as
21 configured figures × 5 questions. Originally, the legacy `site` field held figure
identifiers while `figure_id` was empty and no provenance/review fields existed. The implemented one-time migration:

- renamed the logical topic to `figure_faq` and populated the real `figure_id`;
- added source ID/title/authority/version/section/effective/review/approval fields;
- marked the current reviewed project dataset `approved`;
- removed the obsolete duplicate XLSX file.

The 105 records remain a useful **figure FAQ corpus**, not a comprehensive
forensic-genetics knowledge base; adding institutionally approved SOP/regulatory and
scientific content remains expert-owned work.

## 3. Current Retrieval Findings

### Main chat

Every substantive accepted query now runs `KnowledgeRetriever`, which merges lexical
and vector results, applies `RAG_MAX_DISTANCE`, and includes only approved records.
Low-risk questions can still use qualified model knowledge when no evidence is
relevant; high-risk conclusions require non-figure authoritative evidence.

### Authoritative chat path

The public `/rag/*` endpoints were removed so classification and evidence policy cannot
be bypassed. The `/chat` prompt uses the natural/comprehensive policy and treats
document instructions as untrusted data. Unknown citation IDs are removed; structured
provenance contains only retrieved IDs actually used in the answer.

### Remaining limitation

The current approved collection is still figure-focused. Retrieval and provenance
mechanisms are implemented, but broad trustworthiness depends on institutionally
approved SOP, regulatory, standard, and scientific content being added.

## 4. Recommended Evidence Policy

### Source hierarchy

```text
Approved internal SOP / controlled procedure
→ current Vietnamese law, regulation, standard, or ministry-approved guidance
→ approved national/international forensic standard
→ approved scientific guideline or validated method
→ peer-reviewed literature
→ general model knowledge (low-risk explanation only, clearly qualified)
```

Institutional stakeholders must approve the actual source list. The software must not
label a document authoritative merely because it was uploaded.

### Answer behavior

| Situation | Required behavior |
|---|---|
| Prepared authoritative answer | Return directly with provenance metadata available to audit/client |
| Approved RAG evidence sufficient | Answer naturally and comprehensively; cite each material claim |
| Approved evidence partially sufficient | Answer supported portion; state missing/uncertain portion |
| No sufficient evidence, standard educational question | Qualified model explanation may be allowed by policy, explicitly noting lack of indexed source |
| No sufficient evidence, high-risk question | Do not provide a final conclusion; request data or refer to approved expert/SOP |
| Conflicting approved sources | State conflict and versions/dates; do not silently choose |
| Superseded/withdrawn source | Exclude from retrieval |

## 5. Recommended Knowledge Schema

Split the current figure FAQ from authoritative domain knowledge.

### `figure_faq.tsv` (or equivalent managed source)

Retain the 105 current records, with the misleading `site` field renamed to
`figure_id` during migration.

### Authoritative knowledge records

Recommended logical schema:

```text
id
question
answer
aliases
topic
risk_level
source_id
source_title
source_authority
source_version
source_page_or_section
jurisdiction
effective_date
reviewed_at
reviewer
approval_status
supersedes
content_hash
```

`approval_status` should be constrained, e.g. `draft`, `approved`, `withdrawn`.
Only `approved` and currently effective records enter production retrieval.

PDF/document chunks inherit reviewed source/version/reviewer/approver/access/hash and
page/chunk metadata from the mandatory source manifest. Stable IDs include source
identity and chunk number; deterministic source replacement removes stale versions.
Unmanifested, hash-mismatched, non-approved, restricted, invalid, and unextractable
PDFs fail closed. See `CONTENT_APPROVAL_WORKFLOW.md`.

## 6. Priority Knowledge Expansion

| Priority | Topic |
|---:|---|
| 1 | Laboratory quality assurance, contamination prevention, controls, validation, and result limitations |
| 2 | STR/Y-STR/X-STR interpretation, alleles/loci, artifacts, degradation and inhibition |
| 3 | DNA mixtures, stochastic effects, contributor assumptions and interpretation limitations |
| 4 | Kinship concepts, likelihood ratios, population frequencies and reporting boundaries |
| 5 | mtDNA/SNP/haplogroup use, limitations and population interpretation |
| 6 | Extraction, quantification, PCR, capillary electrophoresis and sequencing workflows |
| 7 | Missing-person and human-remains applications |
| 8 | Chain of custody, integrity, privacy and sensitive genetic-data handling |
| 9 | Reporting language and what the evidence does/does not support |
| 10 | Controlled glossary and reviewed question aliases in Vietnamese/English |

The content program requires forensic-domain owners. The model may help draft or
structure material, but it must not approve its own knowledge. Roles, review gates,
metadata, staged ingestion, and withdrawal procedures are defined in
`CONTENT_APPROVAL_WORKFLOW.md`.

## 7. Retrieval Architecture

Recommended pipeline after semantic domain acceptance:

```text
normalize query + conversation topic
  → retrieve approved/current sources
      ├─ lexical/BM25 channel
      └─ embedding/vector channel
  → merge and deduplicate
  → optional rerank
  → enforce relevance/evidence threshold
  → build bounded context with provenance
  → answer with claim-linked citations
  → validate citation IDs before response
```

### Why hybrid retrieval

- exact terminology, marker names, SOP identifiers and regulation numbers benefit
  from lexical matching;
- paraphrases and natural questions benefit from semantic retrieval;
- combining both is more reliable than unconditional vector top-k.

### Relevance is not domain classification

A low retrieval score must never reclassify an accepted request as out-of-domain.
It only controls evidence sufficiency and answer policy.

## 8. Prompt Policy

Unify main-chat and dedicated-RAG behavior around one evidence policy. The prompt
should require:

1. natural, comprehensive answers whose depth matches the question;
2. explicit distinction between retrieved facts and inference;
3. citations for every material retrieved claim;
4. no invented measurements, thresholds, sources, laws, or case conclusions;
5. explicit insufficient/conflicting evidence language;
6. high-risk abstention when no approved source supports a conclusion;
7. retrieved/user documents treated as untrusted data, never instructions.

Do not duplicate materially different reliability instructions across unrelated
modules. Keep one authoritative policy with small task-specific additions.

## 9. Citation Contract

A citation must be more than an emitted `[knowledge:25]` token.

Recommended response/audit data:

```text
citation_id
source_id
source_title
source_version
page_or_section
content_hash
approval_status
```

Before returning a response:

- reject or remove unknown citation IDs;
- ensure cited records were actually retrieved for this request;
- preserve source/version/page in structured API data or internal audit record;
- test that high-risk claims have at least one approved citation.

## 10. Security and Sensitive Data

- Treat uploaded PDFs, retrieved passages, and user text as untrusted content, not
  system instructions.
- Do not ingest arbitrary uploads into the authoritative corpus without review and
  approval workflow.
- Avoid logging raw genetic profiles, names, case IDs, or unnecessary personal data.
- Define retention, access control, and deletion policy outside the model prompt and
  enforce it at storage/API boundaries.
- Keep all model and retrieval services local unless explicitly approved otherwise.

## 11. Evaluation and Release Gates

Create a reviewed answer-quality set containing:

- questions with one clearly supporting source;
- questions requiring multiple sources;
- no-answer cases;
- conflicting/versioned sources;
- misleading but lexically similar passages;
- prompt injection inside retrieved documents;
- high-risk case conclusions;
- Vietnamese terminology and paraphrases.

Measure:

| Metric | Purpose |
|---|---|
| Retrieval recall@k | Supporting source is found |
| Precision/relevance | Retrieved context is not misleading |
| Citation validity | IDs exist and were retrieved |
| Citation entailment | Source supports the claim |
| Unsupported-claim rate | Hallucination indicator |
| Correct abstention rate | High-risk/no-evidence safety |
| p50/p95 retrieval + generation latency | CPU performance budget |

No corpus expansion should ship solely because answers “look better.” It should pass
source approval and the locked evaluation set.

## 12. Suggested Updates by ROI

| Rank | Update | Effort | ROI |
|---:|---|---:|---|
| 1 | Align RAG prompt with natural comprehensive + strict evidence behavior | Low | **Very high** |
| 2 | Retrieve for every substantive accepted query | Low–Medium | **Very high** |
| 3 | Add high-risk source-required abstention | Low–Medium | **Very high** |
| 4 | Add provenance/approval/version schema and approved-only filtering | Medium | **Very high** |
| 5 | Split figure FAQs from domain corpus | Medium | **High** |
| 6 | Add hybrid retrieval and relevance threshold | Medium | **High** |
| 7 | Validate citation IDs and expose structured provenance | Medium | **High** |
| 8 | Build authoritative topic corpus with expert review | High/ongoing | **High** |
| 9 | Add knowledge lifecycle (effective, superseded, withdrawn) | Medium | **High** |
| 10 | Add answer-grounding evaluation suite | Medium | **Very high** |

## 13. Implemented Files

| File/module | Responsibility |
|---|---|
| `src/knowledge/models.py` | Typed source, approval, version and citation records |
| `src/knowledge/indexer.py` | Controlled TSV/PDF indexing and stable provenance |
| `src/knowledge/retriever.py` | Hybrid retrieval, merge, filtering and thresholds |
| `src/knowledge/citations.py` | Citation validation and structured provenance |
| `src/llm/client.py` | Evidence policy and incremental allowed-citation streaming |
| `src/workflow/nodes.py` | Default retrieval after domain acceptance |
| `src/models/state.py` | Evidence status and citations |
| `src/common/schemas.py` | Optional structured citations in API responses |
| `src/index_documents.py` | Approved/current indexing workflow |
| `tests/test_knowledge.py` | Retrieval, approval/distance and citation correctness |
| `tests/test_integration.py` | Grounded answer, provenance and high-risk behavior |

The mixed TSV was migrated once to the authoritative schema; the duplicate XLSX and
public `/rag/*` upload/query bypass were removed.
