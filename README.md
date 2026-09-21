# Chatbot

Production-oriented, fully offline chatbot for Vietnamese forensic genetics and DNA workflows.

The runtime is Docker-based, CPU-capable by default, and can automatically use an NVIDIA GPU when CUDA is available. All inference, retrieval, persistence, authentication, image handling, and API traffic remain local.

## Quick Start

A first installation uses two files:

- `chatbot-<version>.zip` — application runtime
- `chatbot-models-gemma4-e2b-v2.zip` — model bundle

Place both ZIP files in the same directory. Extract only the runtime ZIP:

```bash
unzip chatbot-<version>.zip
cd chatbot-<version>
sudo make install
```

The installer automatically:

- verifies release checksums and architecture
- loads all Docker images without Internet access
- installs or reuses the required model bundle
- selects NVIDIA GPU when Docker exposes CUDA, otherwise CPU
- preserves persistent credentials and PostgreSQL data
- initializes or reuses configured figures
- applies database migrations
- indexes approved knowledge
- configures Docker startup after reboot
- configures LAN-only firewall access to the public gateway
- starts and verifies the deployment

After installation:

```bash
make status
make verify
make accept
```

The installer prints both URLs when LAN exposure is enabled:

```text
local=http://127.0.0.1:18080
network=http://<LAN-IP>:18080
```

## Host Requirements

The target host currently needs Docker Engine, the Docker Compose plugin, Python 3, `make`, and `unzip` installed before deployment.

Ubuntu x86_64 is the validated production host. NVIDIA GPU acceleration is optional. CPU remains a supported execution path.

Real RHEL-compatible host validation with SELinux Enforcing is future work and is not a blocker for the validated Ubuntu release.

## Public API

Public endpoints:

```text
GET    /live
GET    /ready
POST   /api/v1/chat
POST   /api/v1/chat/stream
DELETE /api/v1/conversations/{conversation_id}
```

`/live` does not require authentication. Other public application endpoints require a Bearer API key.

The persistent client API key is stored at:

```text
~/.local/share/chatbot/state/secrets/chat_api_key
```

Example:

```bash
API_KEY="$(cat "$HOME/.local/share/chatbot/state/secrets/chat_api_key")"

curl -sS \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"STR là gì?"}' \
  http://127.0.0.1:18080/api/v1/chat
```

See [docs/API.md](docs/API.md) for the complete public API contract.

## Common Operations

```bash
make start
make stop
make restart
make status
make logs
make verify
make accept
make cpu
make gpu
make reindex
make reindex-figures
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for details.

## Persistent Data

```text
~/.local/share/chatbot/
├── models/
├── figures/
└── state/
    └── secrets/
```

PostgreSQL data is stored in the Docker volume:

```text
chatbot_postgres_data
```

Runtime release directories are disposable. Code updates do not rotate the API key or require models to be copied again when the required model bundle is already installed.

## Runtime Architecture

Exactly four long-running containers form one Compose project named `chatbot`:

- `chatbot-proxy` — Nginx public gateway
- `chatbot-app` — application/API
- `chatbot-llama` — llama.cpp inference
- `chatbot-postgres` — PostgreSQL + pgvector

Migration and indexing services are one-shot tools, not permanent services.

## Documentation

- [Installation](docs/INSTALL.md)
- [Operations and upgrades](docs/OPERATIONS.md)
- [Public API](docs/API.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Roadmap](docs/ROADMAP.md)
- [Milestones](docs/MILESTONES.md)

## Core Safety Invariants

Risk classification runs before prepared answers or generation. High-risk requests without authoritative evidence return deterministic evidence limitation. Conversation history is context, never evidence. Authenticated identity owns conversations. Internal deployment and Hayhooks management endpoints are not exposed through the production gateway.
