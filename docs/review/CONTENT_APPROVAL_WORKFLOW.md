# Expert Content Approval and Ingestion Workflow

Date: 2026-08-12
Status: **Required operating procedure for future authoritative corpus expansion.**

## 1. Purpose

The chatbot infrastructure can retrieve approved records, cite their provenance, and
abstain from unsupported high-risk conclusions. Its current 105-record corpus is still
primarily figure FAQ content. The next quality improvement is adding institutionally
approved forensic-genetics knowledge without allowing unreviewed material to appear
as an official source.

This document defines the required governance and technical workflow. It does not
approve any SOP, regulation, standard, or scientific publication itself. Approval must
come from authorized Ministry/domain owners.

## 2. Non-Negotiable Rule

A file is not authoritative merely because it exists in `data/documents/`, was
uploaded by an administrator, or was generated/summarized by AI.

A production record may use `approval_status=approved` only when:

1. its source identity and version are verified;
2. its use is legally and institutionally permitted;
3. a qualified domain reviewer checks the extracted claim against the source;
4. an authorized approver accepts it for chatbot use;
5. the reviewer, review date, source section, and effective date are recorded;
6. the record passes retrieval, citation, and answer-quality tests.

If any item is missing, the record remains `draft` and must not enter production
retrieval.

## 3. Roles and Separation of Duties

| Role | Responsibility | May approve own work? |
|---|---|---:|
| Content owner | Owns the SOP/regulation/standard and confirms it is current | No |
| Content editor | Extracts and structures questions, answers, aliases, and metadata | No |
| Forensic reviewer | Verifies scientific and operational accuracy against source | No |
| Authorized approver | Accepts content for chatbot production use | No |
| System operator | Runs validation/indexing and deploys approved records | No |
| Quality/audit reviewer | Samples answers, citations, logs, and lifecycle compliance | No |

For high-risk topics, use at least two people: one qualified forensic reviewer and one
separate authorized approver. The AI may help draft text, generate candidate questions,
or identify duplicates, but it may never be reviewer or approver.

## 4. Source Priority and Eligibility

### Priority order

```text
1. Current approved internal SOP / controlled laboratory procedure
2. Current Vietnamese law, regulation, technical regulation, or official guidance
3. Ministry-approved national/international forensic standard
4. Approved validation report or scientific guideline
5. Peer-reviewed literature accepted by the content owner
6. General educational reference (low-risk background only)
```

### Eligible source checklist

- issuing authority is identifiable;
- title and version/revision are explicit;
- effective and, where applicable, expiry dates are known;
- source is current and not superseded or withdrawn;
- page/section supports each extracted claim;
- licensing permits internal indexing and use;
- classification/access level permits chatbot processing;
- source contains no unnecessary case/person/genetic identifiers;
- source language and translation status are known.

### Never ingest as approved

- public web content without institutional review;
- AI-generated summaries used as their own source;
- obsolete or superseded procedures;
- drafts, meeting notes, email instructions, or informal training slides;
- documents whose authority/version cannot be verified;
- real case files or identifiable genetic profiles;
- content outside the configured forensic-genetics scope;
- documents containing prompt-like instructions intended to control the model.

## 5. Approval States

| State | Meaning | Indexed for production answers? |
|---|---|---:|
| `draft` | Being structured or awaiting review | No |
| `in_review` | Under domain/quality review | No |
| `approved` | Reviewed, authorized, effective, and release-tested | Yes |
| `superseded` | Replaced by a newer approved version | No |
| `withdrawn` | Removed for error, policy, expiry, or incident | No |
| `rejected` | Not suitable for chatbot use | No |

The production manifest accepts only release decisions: `approved`, `superseded`, or
`withdrawn`. Draft, in-review, and rejected artifacts must remain outside the
production documents directory. The runtime retriever includes only `approved`
records; superseded/withdrawn manifests deterministically delete their `source_id`.

## 6. Required Record Metadata

The current TSV supports the core fields below. Future source manifests should retain
all of them and add jurisdiction/supersession/content hashes.

| Field | Required | Example | Rule |
|---|---:|---|---|
| `no` / `id` | Yes | `qa-str-001` | Stable and never reused for another claim |
| `term` / question | Yes | `Stutter được nhận biết như thế nào?` | Natural reviewed question |
| `description` / answer | Yes | Reviewed answer text | Must not exceed source evidence |
| `keywords` | Yes | `STR, stutter, artifact` | Retrieval support only, not scope authority |
| `aliases` | Recommended | Alternate Vietnamese/English questions separated by `|` | Every alias reviewed |
| `topic` | Yes | `str_artifacts` | Controlled vocabulary |
| `figure_id` | Optional | `heatmap1` | Configured figures only |
| `source_id` | Yes | `sop-dna-str` | Stable source identity |
| `source_title` | Yes | Official title | Exact, not invented abbreviation |
| `source_authority` | Yes | Issuing unit/authority | Verified owner |
| `source_version` | Yes | `3.0` | Exact revision/version |
| `source_page_or_section` | Yes | `6.2.3` | Must support the answer |
| `effective_date` | Yes | `2026-01-01` | ISO `YYYY-MM-DD` |
| `reviewed_at` | Yes | `2026-08-12` | ISO `YYYY-MM-DD` |
| `reviewer` | Yes | Approved reviewer identifier | Prefer staff ID/role, not free-form nickname |
| `approval_status` | Yes | `approved` | Production only when truly authorized |
| `jurisdiction` | Future required | `VN` | Legal/operational scope |
| `supersedes` | Future required when applicable | `sop-dna-str@2.0` | Previous source/version |
| `content_hash` | Future required | SHA-256 | Detects unreviewed content changes |

## 7. Content Authoring Rules

Each knowledge answer should:

1. answer one clear question;
2. use terminology from the authoritative source;
3. separate facts, operational requirements, and limitations;
4. identify conditions under which the answer applies;
5. avoid creating thresholds or rules absent from the source;
6. avoid case-specific conclusions;
7. preserve source meaning when translating;
8. cite the exact page/section supporting the claim;
9. state uncertainty or dependencies explicitly;
10. remain understandable without exposing sensitive operational details beyond the
   intended access level.

### Bad record

```text
Question: What threshold should always be used?
Answer: Always use 150 RFU.
Source section: blank
```

Problems: absolute claim, no method/instrument/version context, and no supporting
section.

### Better record pattern

```text
Question: Which analytical threshold applies to method X under SOP version Y?
Answer: Under the stated method and validated configuration, use the threshold
specified in section Z. Do not apply it to another kit, instrument, or validated
configuration without documented validation.
Source: exact SOP/version/section
```

The actual threshold and wording must be copied/derived only from the approved source.

## 8. Review Checklist

### Scientific/domain review

- answer is supported by the cited section;
- terminology and Vietnamese translation are correct;
- method, kit, instrument, population, and scenario limitations are preserved;
- no unsupported extrapolation or official case conclusion is introduced;
- high-risk implications are explicitly identified;
- aliases cannot change the meaning or risk category.

### Governance review

- source/version/effective date are current;
- source owner and access classification are valid;
- reviewer and approver are separate people;
- copyright/licensing and data-handling requirements are satisfied;
- superseded versions are identified;
- no personal, case, profile, or operationally restricted data is included.

### Technical review

- required metadata is present and correctly formatted;
- stable IDs are unique;
- no duplicate or contradictory approved records exist;
- retrieval finds the record for reviewed Vietnamese and English paraphrases;
- irrelevant/adversarial queries do not retrieve it above threshold;
- answer cites only retrieved IDs;
- high-risk no-evidence tests still abstain;
- re-indexing is deterministic and stale versions disappear.

## 9. Staged Ingestion Workflow

```text
source nomination
  → authority/version/access verification
  → draft extraction and metadata
  → forensic review
  → authorized approval
  → isolated indexing environment
  → retrieval/citation evaluation
  → answer and adversarial evaluation
  → production index
  → post-release sampling and monitoring
```

### Step 1 — Nominate one bounded source

Start with one high-value current source, preferably laboratory QA/contamination or a
controlled glossary. Do not begin with the entire document library.

### Step 2 — Create a source register entry

Record source ID, title, authority, version, dates, access level, owner, reviewer,
approver, licensing, and superseded version before extracting content.

### Step 3 — Produce draft records

Create small, atomic question/answer records with `approval_status=draft`. Include
reviewed aliases and exact source sections. AI-assisted drafts must be labeled as such
until human review is complete.

### Step 4 — Review and approve

The forensic reviewer checks every claim against the source. The authorized approver
then changes approved records to `approval_status=approved`. Approval should be a
traceable workflow event, not an untracked text edit.

### Step 5 — Validate outside production

Index into an isolated/staging collection and run:

- parser/schema validation;
- duplicate/conflict checks;
- approved-only checks;
- retrieval recall and relevance tests;
- citation validity and entailment review;
- prompt-injection document tests;
- high-risk abstention tests;
- latency and memory checks.

### Step 6 — Production indexing

Only after release approval:

```bash
make index
```

Verify expected record counts, source/version metadata, and a known set of grounded
questions. Preserve the approved source register and test evidence with the release.

### Step 7 — Post-release review

Sample real non-sensitive questions, inspect source IDs and cited sections, monitor
abstention/irrelevant retrieval rates, and record defects for controlled correction.
Do not silently edit an approved record in place without review and versioning.

## 10. PDF Source Manifest — Implemented

The public API does not accept arbitrary documents. Operator PDF indexing is now
fail-closed and manifest-controlled.

For each production PDF, place one sibling manifest in `data/documents/`:

```text
sop-dna-qa-v1.pdf
sop-dna-qa-v1.manifest.json
```

Use [`SOURCE_MANIFEST_EXAMPLE.json`](SOURCE_MANIFEST_EXAMPLE.json) as the field
reference, replacing every example value with real authorized metadata and the exact
SHA-256 of the reviewed PDF.

Implemented guarantees:

- every PDF requires exactly one `*.manifest.json` entry;
- duplicate `source_id` or PDF references fail the complete indexing run;
- unknown manifest fields and invalid IDs/filenames/dates fail validation;
- reviewer and approver must be different;
- only `internal` content is allowed because the chatbot has no per-user access layer;
- approved files must be effective, reviewed, present, hash-matched, valid PDFs, and
  contain extractable text;
- all manifests and hashes validate before any PDF parsing or database write;
- all approved PDFs parse before any database replacement begins;
- chunks inherit source, version, reviewer, approver, access, and content-hash data;
- stable IDs use `pdf:<source_id>:chunk:<n>`;
- `superseded` and `withdrawn` manifests remove all vectors for the stable `source_id`
  without requiring the old PDF;
- filename alone never establishes authority or approval.

Generate and verify a digest:

```bash
sha256sum data/documents/sop-dna-qa-v1.pdf
```

Then run:

```bash
make index
```

A failure exits non-zero and leaves PDF-backed sources unchanged because validation
and parsing complete before replacement starts. The TSV and figure index stages are
separate; operators should correct the manifest/PDF and rerun the complete index job.

## 11. Update, Supersession, and Withdrawal

### New version

1. ingest as `draft` with a new version and content hash;
2. review differences and affected Q&A records;
3. approve the new version;
4. mark the old version `superseded`;
5. re-index and verify old records are absent;
6. rerun affected evaluation questions.

### Emergency withdrawal

1. identify source/version/record IDs;
2. change status to `withdrawn` or remove from the controlled source;
3. run deterministic source replacement immediately;
4. verify retrieval no longer returns affected records;
5. inspect recent non-sensitive audit metadata for affected citations;
6. notify content owner and document corrective action;
7. release corrected content only after full approval.

## 12. Recommended First Content Release

| Phase | Content | Why first | Suggested size |
|---:|---|---|---:|
| 1 | Controlled glossary and reporting limitations | Low complexity; improves terminology and safe explanations | 30–50 records |
| 2 | QA, controls, contamination, inhibition, degradation | High operational value and safety impact | 40–80 records |
| 3 | STR/Y-STR artifacts and interpretation boundaries | Core forensic workflow | 50–100 records |
| 4 | Kinship/LR concepts and reporting constraints | High value but high risk; needs strict review | 40–80 records |
| 5 | mtDNA/SNP/haplogroup use and limitations | Expands current domain coverage | 30–60 records |
| 6 | Controlled procedure-specific knowledge | Requires access control and source manifests | Source-dependent |

Use quality gates per phase. Do not set a target based only on record count.

## 13. Release Acceptance Criteria

A content release is complete only when:

- [ ] every production record is `approved` and within effective dates;
- [ ] every claim has an exact source/version/page or section;
- [ ] reviewer and approver are traceable and separate;
- [ ] source hashes match reviewed artifacts;
- [ ] superseded/withdrawn records are absent from retrieval;
- [ ] reviewed questions retrieve expected sources;
- [ ] irrelevant questions remain below relevance threshold;
- [ ] structured citations match IDs used in answers;
- [ ] no unsupported high-risk conclusion is produced;
- [ ] prompt injection in source text does not change chatbot policy;
- [ ] unit, live correctness, performance, lint, type, build, and index checks pass;
- [ ] rollback/withdrawal procedure is tested;
- [ ] release evidence is archived for audit.

## 14. Immediate Next Actions

1. Appoint content owner, forensic reviewer, authorized approver, and operator.
2. Select one current, permitted QA/contamination source.
3. Build a source register and 10–20 draft records.
4. Review and approve those records manually.
5. Add a locked retrieval/answer evaluation set for that source.
6. Validate in staging before production indexing.
7. Create the required approved source manifest and verify its SHA-256 before placing
   the first official PDF in `data/documents/`.
