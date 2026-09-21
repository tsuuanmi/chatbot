# Milestones

## Completed

- M0 — Clean repository
- M1 — Minimal Hayhooks / Haystack runtime
- M2 — llama.cpp CPU chat runtime
- M3 — PostgreSQL + pgvector
- M4 — FastEmbed CPU + hybrid retrieval
- M5 — Forensic domain, risk, evidence, prepared answers, citations, and RAG
- M6A — Conversation persistence and bounded context
- M6B.1 — Offline API authentication
- M6B.2 — Authenticated conversation ownership
- M6B.3 — Authentication hardening
- M6C — Streaming API
- M7 — Nginx and production hardening
- M8.1 — Universal offline runtime bundle
- M8.2 — Offline installer
- M8.3 — Offline operations
- M9 — Optional NVIDIA GPU acceleration
- M10 — Cleanup, universal release architecture, Ubuntu release acceptance, MTP
- M11 — Multimodal configured figures and transient image input
- Deployment UX / Host Hardening — stable public API, persistent API key, LAN firewall, Docker boot startup, reboot recovery

## Current Validated Release

Ubuntu x86_64 has completed runtime installation, upgrade, CPU/GPU parity, multimodal acceptance, public API acceptance, persistent-state acceptance, LAN firewall acceptance, Docker restart recovery, and stable API-key acceptance.

The runtime architecture uses one Compose project named `chatbot`, four long-running containers, one independently versioned model package, stable persistent stores, and one public Nginx gateway.

## Future Work

Real RHEL-compatible host validation with SELinux Enforcing remains future work.

Fully offline installation of operating-system prerequisites is also future work; the runtime artifact assumes Docker Engine, Docker Compose, Python 3, make, and unzip are already installed.
