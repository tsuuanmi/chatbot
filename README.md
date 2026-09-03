# Chatbot

Vietnamese forensic-genetics chatbot powered by Gemma-4-E2B, EmbeddingGemma,
LangGraph, ChromaDB, and PostgreSQL. It supports prepared answers, approved RAG,
precomputed figure descriptions, multimodal input, conversation history, and
streaming responses.

## Architecture

```text
Client
  └─ FastAPI
      └─ answer cascade
          ├─ prepared answer
          ├─ precomputed configured-figure answer
          ├─ semantic domain/risk decision
          ├─ approved evidence retrieval
          └─ Gemma generation or evidence limitation

Internal services
  ├─ llama.cpp Gemma server
  ├─ llama.cpp EmbeddingGemma server
  ├─ ChromaDB
  └─ PostgreSQL
```

Online development publishes FastAPI directly. Offline deployment publishes only
an API-key-authenticated HTTP Nginx gateway on the trusted LAN; the API, models,
ChromaDB, and PostgreSQL remain on private Docker networks.

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/api.md`](docs/api.md) for the system and HTTP contracts.

## Required models

Place these files in `models/`:

```text
models/
├── gemma-4-E2B-it-Q4_K_M.gguf
├── mmproj-gemma-4-E2B-it-bf16.gguf
├── mtp-gemma-4-E2B-it.gguf
└── embeddinggemma-300M-Q8_0.gguf
```

Download commands:

```bash
mkdir -p models

curl -L "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/0314792d7f1f7e229411f620751375812bb9faf2/gemma-4-E2B-it-Q4_K_M.gguf" \
  -o models/gemma-4-E2B-it-Q4_K_M.gguf
curl -L "https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/resolve/b4243c156154b6dca9324415f8c7ccc098b4aed1/mmproj-gemma-4-E2B-it-bf16.gguf" \
  -o models/mmproj-gemma-4-E2B-it-bf16.gguf
curl -L "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/0314792d7f1f7e229411f620751375812bb9faf2/mtp-gemma-4-E2B-it.gguf" \
  -o models/mtp-gemma-4-E2B-it.gguf
curl -L "https://huggingface.co/unsloth/embeddinggemma-300m-GGUF/resolve/6661a6504c30d8304af13455cb4a5d4f5bc6011f/embeddinggemma-300M-Q8_0.gguf" \
  -o models/embeddinggemma-300M-Q8_0.gguf
```

Deployment supports CPU and NVIDIA GPU profiles. The offline installer selects the
profile explicitly with `--gpu yes|no` (`yes` requires a supported 6 GiB NVIDIA GPU,
the NVIDIA driver, and NVIDIA Container Toolkit and fails if unavailable; `no` runs
CPU-only). The online
development flow (`make start`) still supports `ACCELERATOR=auto|cpu|gpu`, where
`auto` uses GPU only when the NVIDIA driver, Docker NVIDIA runtime, and CUDA container
validation succeed; otherwise it uses CPU.
CPU is correctness-compatible but substantially slower for generation and multimodal
indexing.

## Configuration

`.env.example` is a ready-to-use local configuration template. For a new checkout:

```bash
cp .env.example .env
```

No value must be changed for the standard local Docker setup. Development FastAPI
binds to `127.0.0.1` by default; use the authenticated offline gateway for LAN
access. Adjust GPU layers, ports, model names, or generation settings only when the
host requires it. The root `.env` is the canonical active configuration in both
modes: online setup copies `.env.example`, while the offline installer generates
`.env` from `config/offline.env.template` with target paths and secrets.

## Make interface

`MODE` defaults to `online`. The same lifecycle commands support both deployment
modes:

```bash
make setup
make start                         # online development stack; auto profile
make start ACCELERATOR=cpu         # CPU-only online stack
make start ACCELERATOR=gpu         # require the NVIDIA GPU profile
make status ACCELERATOR=cpu
make index ACCELERATOR=cpu
make stop ACCELERATOR=cpu

make start MODE=offline            # installed offline stack
make status MODE=offline
make index MODE=offline
make stop MODE=offline

make format
make check
make clean
```

`make check` runs Ruff, mypy, compile checks, and isolated tests. Compose definitions
are maintained only under `compose/`; use the Make targets or deployment scripts, which
select the required base/CPU/GPU files with an explicit repository project directory.
Do not use bare `docker compose` discovery or copy a selected Compose file to the
repository root. Live integration and performance suites remain explicit pytest
operations because they require a running stack:

```bash
.venv/bin/pytest -q -s -rA -m "integration and not performance"
.venv/bin/pytest -q -s -rA -m performance
```

## Online development

```bash
cp .env.example .env
make start                         # auto-select CPU or GPU
# or: make start ACCELERATOR=cpu
# or: make start ACCELERATOR=gpu
```

This builds the application image, starts healthy services, indexes approved
knowledge, and precomputes configured-figure descriptions.

Check the API:

```bash
curl http://localhost:8080/api/v1/health
```

Send a question:

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"STR là gì?"}'
```

Stream a response:

```bash
curl -N -X POST http://localhost:8080/api/v1/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"Trong giám định ADN pháp y, mtDNA được sử dụng như thế nào?"}'
```

## Offline preparation

On the Internet-connected preparation computer:

```bash
cd /home/superman/workspaces/chatbot
make prepare
```

Output:

```text
/home/superman/workspaces/chatbot.zip   committed Git HEAD source and installer
/home/superman/workspaces/images.zip    exported Docker runtime images
/home/superman/workspaces/models.zip    the four GGUF model files with checksums
```

Preparation requires a clean Git working tree and the four GGUF files present in
`models/`. Application source is read from `git archive HEAD`, and the release
manifest records that commit. The GGUF models are packaged into `models.zip` with a
`SHA256SUMS` file; they are not part of `chatbot.zip` or `images.zip`. Python
runtime dependencies, including those used to index documents and figures, are already
installed in the application image inside `images.zip`. The image archive includes
both pinned CPU and CUDA llama.cpp servers so one release can install on either host
type.

Supported offline targets are Ubuntu 22.04 LTS, Ubuntu 26.04 LTS, and Red Hat
Enterprise Linux 8.10, all with rootful Docker Engine and the Compose plugin; Podman
is not supported. Docker must expose its IPv4 `DOCKER-USER` iptables chain for LAN
port isolation. RHEL keeps SELinux Enforcing and uses firewalld.

On the dedicated target computer, extract all three ZIPs into the same directory:

```bash
cd /home/superman/workspaces
unzip /path/to/chatbot.zip
unzip /path/to/images.zip
unzip /path/to/models.zip
cd chatbot
./install.sh --gpu no          # CPU profile
# or: ./install.sh --gpu yes   # require the NVIDIA GPU profile
```

The installer detects the primary LAN IPv4 address and subnet, removes only containers
and volumes bearing this release folder's path-derived Compose project label, preserves
unrelated Docker resources, images, and GGUF models, and generates five client
credentials. Resources from a
previous naming scheme require the explicit migration utility documented in
`docs/offline.md`; the installer does not guess them. It configures LAN-only host
firewall rules (UFW on Ubuntu, firewalld on RHEL) and Docker port isolation, and enables
Docker boot startup. Numbered progress is shown on screen and
saved to `install.log`;
figure descriptions report per-figure progress during the first index.

Nginx listens on HTTP port 80 on all host IPv4 interfaces by default. Clients use
the detected target address, such as `http://192.168.1.50`, plus their individual API
key. Reserve the target address in DHCP so client URLs stay stable. HTTP traffic and
API keys are unencrypted, so this mode is limited to an isolated, trusted LAN. Follow
[`docs/offline.md`](docs/offline.md) for target prerequisites, LAN clients, API keys,
firewall behavior, reboot recovery, operations, backups, and troubleshooting.

## Knowledge and figures

Prepared answers live in `data/documents/knowledge_base.tsv`. Approved PDFs require
reviewed source manifests before indexing. Configured figures live in
`data/figures/` and are described once during `make index`.

Knowledge ingestion is operator-controlled; there is no public upload endpoint.
See [`docs/review/CONTENT_APPROVAL_WORKFLOW.md`](docs/review/CONTENT_APPROVAL_WORKFLOW.md).

## Documentation

- [`docs/README.md`](docs/README.md): documentation index.
- [`docs/api.md`](docs/api.md): HTTP and SSE contract.
- [`docs/architecture.md`](docs/architecture.md): system boundaries and data flow.
- [`docs/offline.md`](docs/offline.md): complete offline deployment guide.
- [`docs/src/`](docs/src/): one-to-one manual for every `src/**/*.py` file.
- [`docs/review/`](docs/review/): content and behavior review records.
