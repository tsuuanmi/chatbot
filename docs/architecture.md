# Architecture

## Deployment Boundary

The system has separate development and offline-production Compose paths. The four
Compose definitions are kept only in `compose/`; lifecycle scripts explicitly select
the base definition and optional GPU overlay with the repository root as the Compose
project directory. Development publishes FastAPI on loopback port 8080 by default.
Offline production publishes only an API-key-authenticated HTTP Nginx gateway on the
target's trusted LAN interfaces;
all application and data services use an internal Docker network without an external
route.

```text
Trusted LAN :80
  └─ nginx (body/rate limits)
      └─ chatbot:8080 (FastAPI, bearer API keys)
          ├─ llama-server:8080      authenticated internal HTTP
          ├─ embedding-server:8080  authenticated internal HTTP
          ├─ chromadb:8000          internal HTTP, sole vector persistence owner
          └─ postgres:5432          internal TCP, owner-scoped conversations
```

The llama.cpp model service loads:

- `gemma-4-E2B-it-Q4_K_M.gguf` (main LLM)
- `mmproj-gemma-4-E2B-it-bf16.gguf` (multimodal projector)
- `mtp-gemma-4-E2B-it.gguf` (MTP drafter)

The embedding service loads `embeddinggemma-300M-Q8_0.gguf`. All four files live in `models/` and are pinned by name via `LLAMA_MODEL_NAME`, `MMPROJ_MODEL`, `MTP_MODEL_NAME`, and `EMBEDDING_MODEL_NAME` in `.env`. Model files are downloaded with the README setup commands.

MTP speculative decoding is available with `--spec-type draft-mtp`. Deployment uses
a CPU-safe base Compose file and a GPU override. The offline installer selects the
profile explicitly with `--gpu yes|no` (`yes` requires and validates a supported 6 GiB
NVIDIA GPU, host runtime, and CUDA image, failing rather than falling back; `no` is
CPU-only) and persists it to
`.env`. The online development flow (`make start`) still supports
`ACCELERATOR=auto|cpu|gpu`, where `auto` selects GPU only when its NVIDIA host
prerequisites and CUDA container validation succeed; otherwise it uses CPU. The
validated GTX 1660 Super GPU
profile uses one generation slot, 16 main-model GPU layers, an 8192-token context,
full EmbeddingGemma offload, and draft offload disabled; CPU uses zero offload layers.

Internal model services require separate API keys. Offline FastAPI requires a hashed
client API key, scopes conversation storage by client owner, and is reachable only
through Nginx. Installation creates five client identities by default. CORS is
configured from `CORS_ORIGINS`; it is not used as access control. Offline HTTP traffic
is unencrypted and is intended only for an isolated, trusted LAN. Ubuntu uses UFW and
RHEL uses firewalld; both use a persistent `DOCKER-USER` chain to restrict published HTTP
to the detected LAN. RHEL keeps SELinux Enforcing and labels Compose bind mounts. PostgreSQL,
ChromaDB, FastAPI, and model ports are not published by the offline deployment.

## Primary Chat Flow

There is one authoritative chat implementation in `src/workflow/`. Answers are resolved by a **priority cascade**: the most authoritative source wins, and the LLM is the universal fallback for in-domain questions.

```text
START
  → find_prepared_answer
      ├─ hit → END                         (prepared_answer, no LLM)
      └─ miss → resolve_figure_description
          ├─ direct configured figure → END (figure_prepared, no LLM/image encode)
          └─ load persisted domain context → EmbeddingGemma classifier
              ├─ OUT_OF_DOMAIN → END       (no full history/RAG/Gemma)
              ├─ CLARIFY → END             (bounded clarification request)
              └─ IN_DOMAIN → load_history → retrieve approved evidence
                  → aggregate_context → END
```

### Answer Priority Cascade

1. **Prepared answer** — an exact match from `knowledge_base.tsv` is returned directly. This is the most authoritative and cheapest path; the LLM is never invoked.
2. **Precomputed figure answer** — a direct request for a configured figure returns its indexed description before domain/history/RAG/model work. More specific questions use that description as model text context.
3. **Semantic domain classification** — EmbeddingGemma-300M emits typed `IN_DOMAIN`, `OUT_OF_DOMAIN`, or `CLARIFY` plus `STANDARD`/`HIGH_RISK`. It is the only production domain authority. One persisted prior decision resolves neutral follow-ups without full history. Arbitrary images without established forensic relevance clarify rather than auto-accept. Classifier failure returns HTTP 503 and never defaults to in-domain.
4. **Approved evidence retrieval** — every substantive accepted query runs hybrid lexical/vector retrieval. Only `approved` records within `RAG_MAX_DISTANCE` enter context. Retrieval never changes the domain decision; it controls evidence sufficiency. Source/version/section metadata is returned only for citations actually used.
5. **Evidence-aware generation** — standard low-risk questions may use qualified model knowledge when approved evidence is absent. High-risk identity, kinship, case, SOP, or legal conclusions require non-figure authoritative evidence or return an explicit limitation. Retrieved/user content is untrusted data, not instructions.

### Precomputed Figure Answers

Configured figures in `data/figures/` are described once through the multimodal
(mmproj) model at index time. Descriptions are stored in the dedicated
`chatbot_figures` ChromaDB collection under stable IDs and content hashes. Runtime
requests perform exact ID lookup instead of re-encoding immutable images:

- **Direct description or analysis** (`Mô tả hình bar3`, `Phân tích heatmap1`) →
  stored description verbatim with `source=figure_prepared`.
- **Specific question** (`So sánh bar3 với...`, `Tại sao heatmap1...`) → stored
  description becomes text context for a generated answer without image encoding.
- **No stored description** → explicit indexing error; run `make index`. There is
  intentionally no hidden runtime multimodal fallback for configured figures.
- **Attached user images** always stay on the multimodal path.

The graph prepares a direct answer or model context. Answer resolution is deliberately outside graph nodes so non-streaming and streaming endpoints share preparation but use the correct generation mode:

- `run_workflow()` calls `LLMClient.chat()` once.
- `stream_workflow()` returns the same prepared state and a real `LLMClient.stream_chat()` token generator.
- Prepared answers, precomputed figure answers, clarifications, and out-of-domain responses return one direct chunk without invoking the LLM.

The API persists the completed answer once. Streaming persistence occurs only after generation completes.

## Response Classification

Every chat response has an explicit source:

| Source | Meaning |
|---|---|
| `prepared_answer` | Exact authoritative TSV match; LLM bypassed |
| `figure_prepared` | Stored precomputed description for a configured figure; LLM and image encode bypassed |
| `generated` | Gemma answer for an in-domain question, optionally grounded in ChromaDB and figures |
| `out_of_domain` | Semantic classifier rejected the question; conversation ended |
| `clarification` | Scope/context is ambiguous; one bounded clarification is requested |

## Source Responsibilities

[`docs/src/`](src/) mirrors every `src/**/*.py` file one-to-one and records each
module's responsibilities, boundaries, API, dependencies, errors, and tests. See
[`source-layout.md`](source-layout.md) for the package-level dependency map.

## Dependency Boundaries

- API modules depend on workflow/RAG/history services, not concrete storage clients.
- Workflow nodes use tool and history service interfaces.
- RAG service receives a vector database dependency.
- Chroma is accessed only over HTTP; application processes never open Chroma persistence files.
- Blocking PDF, embedding, vector, and image work is moved off the event loop where it occurs in async paths.
- PostgreSQL turn allocation is guarded by an owner/conversation-scoped advisory lock; every history operation includes the authenticated owner.

## Data and Input Safety

- Prepared questions: `data/documents/knowledge_base.tsv`.
- Figures: read-only mount at `data/figures`; identifiers allow only letters, digits, `_`, and `-`.
- Client images: base64/data URLs only; server filesystem paths are rejected.
- Knowledge ingestion is operator-controlled; no public upload route can enter the approved evidence collection.
- Every PDF requires a strict reviewed source manifest and exact SHA-256. All manifests,
  hashes, and PDF extraction validate before any PDF-backed source is replaced.
- Only internal approved content is indexable; withdrawn/superseded manifests delete
  the stable source deterministically.
- Unexpected API errors are logged internally and sanitized for clients.

## Deliberately Removed Layers

The following had no authoritative runtime role and were deleted:

- `ChatEngine`
- expert switching endpoints
- `BaseExpert`, `QnaExpert`, and `RAGBotExpert`
- duplicate exact-match implementations
- synchronous memory abstractions over async PostgreSQL
- legacy SSE event helpers
- `AnswerGenerator` compatibility alias
- MCP compatibility protocol and unused schemas
- `input` request alias and `additional_kwargs`

## Startup and Shutdown

FastAPI lifespan:

1. Creates application dependency bindings.
2. Connects and migrates PostgreSQL, including client ownership.
3. Functionally checks local model, embedding, ChromaDB, and PostgreSQL services.
4. Embeds and caches all semantic classifier prototypes with bounded retries.
5. Serves requests only after warmup succeeds.
6. Closes PostgreSQL, LLM, and embedding clients on shutdown.

Offline installation removes recognized legacy chatbot containers and their
volumes for a fresh database, preserves unrelated Docker resources and all images/models,
starts healthy backend services, runs the incremental figure indexer, configures
persistent LAN firewall rules, then starts FastAPI and the HTTP gateway. Docker is
enabled at boot and every long-running service uses `restart: unless-stopped`, so the
stack returns after power restoration without rerunning the one-shot indexer. Routine
offline startup uses preloaded images with `--no-build --pull never`. Public `/live`
reports process liveness; authenticated `/ready` verifies dependencies, classifier
warmup, and required indexes.
