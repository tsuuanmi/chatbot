# Roadmap

## Mission

Maintain a clean, production-oriented, fully offline Vietnamese forensic genetics chatbot with deterministic safety policy, local evidence retrieval, authenticated conversations, multimodal support, and reproducible deployment.

CPU remains a supported reference execution path. NVIDIA GPU acceleration may improve performance but must not alter API, policy, retrieval, authentication, ownership, evidence handling, or output semantics.

## Current Architecture

Long-running services:

1. Nginx public gateway
2. Chatbot application
3. llama.cpp
4. PostgreSQL + pgvector

One-shot tools handle migrations, knowledge indexing, configured-figure indexing, installation, and validation.

Runtime releases and model releases have independent lifecycles.

Persistent deployment state lives outside versioned runtime directories.

## Completed Scope

The current Ubuntu release includes:

- fully offline runtime operation
- CPU and NVIDIA GPU execution
- Gemma 4 main model, multimodal projector, and MTP draft model
- PostgreSQL + pgvector persistence
- FastEmbed CPU embeddings
- PostgreSQL full-text + semantic retrieval fused with RRF
- prepared answers and approved-evidence RAG
- deterministic forensic domain and high-risk policy
- validated citations
- authenticated conversation ownership
- bounded one-sitting conversation context
- non-streaming and SSE public APIs
- configured figures with persistent description cache
- transient base64 image input
- universal offline runtime ZIP
- independent model ZIP
- persistent models, figures, secrets, and PostgreSQL data
- stable API key across upgrades and reboot
- automatic CPU/GPU selection
- Nginx LAN gateway
- persistent Docker `DOCKER-USER` LAN firewall
- Docker startup and automatic runtime recovery after restart/reboot
- Ubuntu release acceptance

## Production Public API

```text
GET    /live
GET    /ready
POST   /api/v1/chat
POST   /api/v1/chat/stream
DELETE /api/v1/conversations/{conversation_id}
```

Framework/runtime-management endpoints are internal and are not part of the public contract.

## Safety Invariants

Risk classification runs before prepared answers. High-risk requests without authoritative evidence do not call the LLM. Conversation history is context, not evidence. Historical citations are not automatically valid for a new turn. Authenticated identity determines conversation ownership. Raw image input cannot bypass domain or risk policy and is not persisted as base64 content.

## Future Work

The following are useful future improvements but are not blockers for the validated Ubuntu release:

- real RHEL/Rocky/AlmaLinux acceptance with SELinux Enforcing
- fully offline bootstrap of host OS prerequisites
- TLS for deployments that are not on an isolated trusted LAN
- an explicit policy for optional VPN/Tailscale API access when required
- continued dependency and embedding reproducibility review

## Deliberately Excluded

Do not add generic infrastructure without a concrete product requirement. The core does not require autonomous agents, web browsing, MCP, Redis, Celery, Kubernetes, Open WebUI, or generic workflow engines.
