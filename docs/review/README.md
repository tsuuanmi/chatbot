# Review Index — Trust, Domain Control, Knowledge, and Performance

Date: 2026-08-12
Status: **Core classifier, strict behavior, approved retrieval, provenance, and citation recommendations implemented. Authoritative corpus expansion remains ongoing.**

This directory records code-grounded reviews of the forensic-genetics chatbot.
Deployment supports selectable CPU and NVIDIA CUDA profiles; older measurements are
retained as historical baselines. The implementation includes the semantic classifier and evidence-aware
pipeline described below. Domain-expert expansion and approval of additional
forensic-genetics sources remains institutional content work.

## Reviews

| Document | Scope |
|---|---|
| [`DOMAIN_BEHAVIOR_REVIEW.md`](DOMAIN_BEHAVIOR_REVIEW.md) | Semantic domain classifier, strict scope, high-risk behavior, adversarial evaluation, rollout |
| [`KNOWLEDGE_RAG_REVIEW.md`](KNOWLEDGE_RAG_REVIEW.md) | Approved-source retrieval policy, corpus structure, provenance, citations, lifecycle, evaluation |
| [`CONTENT_APPROVAL_WORKFLOW.md`](CONTENT_APPROVAL_WORKFLOW.md) | Expert roles, source eligibility, metadata, review, staged ingestion, supersession, withdrawal, and release gates |
| [`PERFORMANCE_REVIEW.md`](PERFORMANCE_REVIEW.md) | Verified correctness and latency, including implemented figure precomputation |

## Current Findings

1. EmbeddingGemma-300M is now the sole production domain authority, with constrained
   `IN_DOMAIN`, `OUT_OF_DOMAIN`, and `CLARIFY` labels plus separate risk decisions.
2. Every accepted substantive request attempts approved hybrid evidence retrieval;
   high-risk conclusions abstain without non-figure authoritative evidence.
3. The packaged 105-entry TSV has provenance and approval metadata but remains a
   figure FAQ corpus (21 figures × 5 records), not broad expert knowledge.
4. Public upload/query bypasses are removed; `make index` is the controlled operator
   ingestion path.
5. Adding expert content is now the highest-value improvement, but content must be
   reviewed and authorized by qualified people. AI may draft but cannot approve.
6. Mandatory reviewed PDF source manifests and content-hash checks are implemented.
   Unmanifested, altered, restricted, invalid, or unapproved PDFs fail indexing;
   filename-derived metadata never establishes authority.
7. Configured-figure behavior is accepted as complete for now.

## Suggested Updates by ROI

| Rank | Update | Value | Effort | ROI |
|---:|---|---|---:|---|
| 1 | Build a constrained lightweight semantic domain classifier | Blocks tricky/broad out-of-domain prompts more intelligently than keywords | Medium | **Very high** |
| 2 | Create a labeled Vietnamese domain/adversarial evaluation set | Makes classifier quality measurable and safe to release | Medium | **Very high** |
| 3 | Make approved-source RAG the default for substantive accepted questions | Reduces unsupported model-only answers | Medium | **Very high** |
| 4 | Add high-risk answer policy and source-required abstention | Prevents unsupported case, identity, kinship, procedure, and legal conclusions | Low–Medium | **Very high** |
| 5 | Align main and dedicated RAG prompts | Produces natural, comprehensive, evidence-bound answers consistently | Low | **Very high** |
| 6 | Add source provenance, approval state, version, page/section, and reviewer metadata | Makes answers auditable and maintainable | Medium | **High** |
| 7 | Split figure FAQs from authoritative forensic-genetics knowledge | Removes mixed corpus responsibilities and improves retrieval quality | Medium | **High** |
| 8 | Add hybrid retrieval, relevance filtering, and citation validation | Prevents weak vector matches from contaminating answers | Medium | **High** |
| 9 | Normalize prepared-answer matching with explicitly reviewed aliases | Improves authoritative answer coverage without unsafe fuzzy matching | Low | **High** |
| 10 | Add prompt-injection, sensitive-data, and audit behavior | Important for public-security and genetic-data handling | Medium | **High** |
| 11 | Lower generation temperature and pin model/prompt versions | Improves repeatability and auditability | Low | **Medium–high** |
| 12 | Add reliability observability without logging unnecessary sensitive content | Supports incident analysis, drift detection, and quality review | Medium | **Medium–high** |

## Recommended Next Phase

The reliability pipeline is implemented. The next phase is a controlled expert-content
program:

```text
select current permitted source
  → register authority/version/access/hash
  → create draft atomic records
  → independent forensic review
  → separate authorized approval
  → staging index and locked evaluation
  → production `make index`
  → post-release sampling and lifecycle review
```

Start with a single QA/contamination source and 10–20 records. Do not bulk-import the
document library. See `CONTENT_APPROVAL_WORKFLOW.md` for the complete operating and
release procedure.
