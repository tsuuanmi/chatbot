# Python Source Layout

Every `src/**/*.py` file has an exact same-path Markdown manual under `docs/src/`.
For example, `src/api/v1/chat.py` maps to `docs/src/api/v1/chat.md`, and
`src/api/__init__.py` maps to `docs/src/api/__init__.md`.

```text
src/
├── api/                 FastAPI lifecycle, authentication, capacity, health, chat, SSE
├── base/components/     Embedding and vector-database interfaces and adapters
├── common/              shared schemas, exceptions, exact match, knowledge parsing
├── config/              validated environment settings
├── database/            PostgreSQL persistence and conversation-history service
├── domain/              semantic domain and risk classification
├── figures/             configured-figure description indexing and storage
├── knowledge/           controlled indexing, retrieval, provenance, and citations
├── llm/                 llama.cpp generation and streaming client
├── models/              shared LangGraph state
├── tools/               safe configured-figure loading
├── workflow/            answer-cascade graph, nodes, edges, and routing
├── container.py         dependency construction and shutdown
├── index_documents.py   operator-controlled index orchestration
└── readiness.py         startup warmup and functional readiness checks
```

## Dependency direction

```text
api -> workflow + database + readiness
workflow -> common + domain + figures + knowledge + llm + database + tools
container -> concrete clients, stores, services, and workflow dependencies
knowledge/figures -> embedding + vector database + controlled local data
llm/embedding/vector adapters -> internal HTTP services
```

API transport does not own model or storage configuration. Workflow code does not
publish HTTP routes. ChromaDB alone owns vector persistence files, and PostgreSQL
alone owns conversation persistence.

## Mirror enforcement

`tests/test_docs_mirror.py` compares both sets of paths. It fails when a source file
has no manual or when `docs/src/` contains an orphaned manual. Semantic changes
should update the source file and its manual in the same commit.
