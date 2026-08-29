# Offline Deployment and Operations

## 1. Delivery model

The final deliverable is three files created on an Internet-connected preparation
computer:

```text
/home/superman/workspaces/chatbot_bca.zip   committed Git HEAD source and installer
/home/superman/workspaces/images.zip    exported Docker runtime images
/home/superman/workspaces/models.zip    the four GGUF model files with checksums
```

Extract all three ZIPs into the same parent directory. Together they create a normal
repository-like directory:

```text
chatbotbca/
├── src/                         application source
├── docs/                        operator and API documentation
├── config/                      static templates and generated secrets
├── scripts/install.sh           canonical installer source
├── scripts/offline/             start, stop, client, backup, restore tools
├── data/                        packaged knowledge and configured figures
├── tests/                       source-level tests
├── images/runtime-images.tar    preloaded application and service images
├── models/                       the four GGUF model files extracted from models.zip
├── docker-compose.offline.yml    CPU-safe base profile
├── docker-compose.offline.gpu.yml NVIDIA GPU override
├── release-manifest.json
├── SHA256SUMS
└── install.sh                   generated one-command target entry point
```

`chatbot_bca.zip` contains source read from the committed `git archive HEAD`, plus
the generated release manifest, checksums, and root installer. `images.zip` contains
only `chatbotbca/images/runtime-images.tar`. `models.zip` contains
`chatbotbca/models/` with the four GGUF files and a `SHA256SUMS` file. All three
ZIPs exclude Git metadata, secrets, virtual environments, caches, runtime databases,
and backups.

Extracting `models.zip` places these four files in `chatbotbca/models/`:

```text
gemma-4-E2B-it-Q4_K_M.gguf
mmproj-gemma-4-E2B-it-bf16.gguf
mtp-gemma-4-E2B-it.gguf
embeddinggemma-300M-Q8_0.gguf
```

The installer verifies the four filenames and their `SHA256SUMS` checksums. Model
downloading is the operator's responsibility at preparation time.

## 2. Offline architecture

```text
Trusted LAN client
       |
       | HTTP + client API key
       v
Nginx :80
       |
       | private Docker network
       v
FastAPI chatbot
   ├── llama.cpp Gemma server       answer and figure generation
   ├── llama.cpp EmbeddingGemma     classification and retrieval vectors
   ├── ChromaDB                     knowledge and figure indexes
   └── PostgreSQL                   owner-scoped conversation history
```

Only Nginx publishes a host port. FastAPI, llama.cpp, EmbeddingGemma, ChromaDB,
and PostgreSQL are not directly reachable from the LAN.

The target does not run `docker build`, `docker pull`, `uv sync`, or any package
download during setup or normal operation. It loads all runtime images from
`images/runtime-images.tar` and starts with `--no-build --pull never`.

The host `.venv` is intentionally excluded. The application image already contains
its own `/app/.venv` with all locked runtime dependencies. Installation and
`make index MODE=offline` run `python -m src.index_documents` through the image's
`indexer` service, which indexes documents and precomputes figure descriptions.

## 3. Target requirements

Supported target profile:

- Ubuntu 26.04 LTS x86_64;
- Intel i7-9700K class CPU or better and 32 GB RAM;
- at least 20 GB free SSD space plus backup space, subject to final dual-image archive measurement;
- Docker Engine and Docker Compose plugin;
- UFW, iptables, systemd, and sudo access for automatic host security/startup setup;
- `unzip`, `openssl`, `curl`, `python3`, `sha256sum`, `tar`, `ip`, `awk`, and `tee`;
- for GPU mode only: NVIDIA GTX 1660 Super 6 GB or better, NVIDIA driver, NVIDIA
  Container Toolkit, and `nvidia-smi`;
- a dedicated chatbot host: installation removes recognized legacy Chatbot BCA
  containers and their attached/orphaned Docker volumes for a fresh database; unrelated
  containers and volumes, Docker images, GGUF models, and source files are preserved;
- a reserved/static LAN IPv4 address is recommended so client URLs remain stable.

Check before transfer:

```bash
docker version
docker compose version

# GPU mode only
nvidia-smi
docker info --format '{{json .Runtimes}}'
```

GPU mode requires `nvidia` in the final Docker-runtime output. CPU mode has no NVIDIA
host requirement.

## 4. Create the release ZIPs

On the preparation computer:

```bash
cd /home/superman/workspaces/chatbotbca
make prepare
```

The builder:

1. refuses modified, deleted, staged, or untracked working-tree files;
2. exports the exact committed source with `git archive HEAD`;
3. pulls third-party images pinned by digest;
4. builds the Chatbot BCA application image from that committed source;
5. exports all runtime images to `images/runtime-images.tar`;
6. records the source commit and required image tags in `release-manifest.json`;
7. creates `SHA256SUMS` for source/configuration files and a separate
   `models/SHA256SUMS` for the GGUF files; the large Docker image archive is
   intentionally not checksummed;
8. creates and integrity-checks all three ZIPs before publishing them, and removes
   already-published outputs if publishing a later one fails.

Commit and review every intended change before running `make prepare`. There is no
dirty-tree override because `chatbot_bca.zip` must identify one exact Git commit.
Remove all three old outputs before rebuilding:

```bash
rm -f /home/superman/workspaces/chatbot_bca.zip \
      /home/superman/workspaces/images.zip \
      /home/superman/workspaces/models.zip
make prepare
```

## 5. Transfer and extract

Use exFAT or ext4 media, not FAT32. Copy `chatbot_bca.zip`, `images.zip`, and
`models.zip`.

On the target, extract all three ZIPs from the same parent directory so they merge
into one `chatbotbca/` folder:

```bash
mkdir -p /home/superman/workspaces
cd /home/superman/workspaces
unzip /media/$USER/<USB>/chatbot_bca.zip
unzip /media/$USER/<USB>/images.zip
unzip /media/$USER/<USB>/models.zip
cd chatbotbca
```

The result should be:

```text
/home/superman/workspaces/chatbotbca
```

The four GGUF model files and their `SHA256SUMS` are placed in:

```text
/home/superman/workspaces/chatbotbca/models
```

## 6. Run the installer

Reserve the target's LAN IPv4 address in the router when possible. The installer
uses JSON output from `ip` to select the address used by the default route, ignores
Docker/Tailscale virtual interfaces during automatic selection, requires an operational
link with carrier, derives the interface subnet, and prints both values before changing
the host. The deployed isolated LAN may use a globally numbered range such as
`172.119.37.0/24`; the installer trusts the directly connected interface prefix rather
than requiring RFC1918 addressing. Verify that this subnet is physically isolated.

Install from a local target terminal so the sudo prompt is visible:

```bash
cd /home/superman/workspaces/chatbotbca
chmod +x install.sh
./install.sh --gpu no             # CPU profile, no NVIDIA requirement
# or: ./install.sh --gpu yes      # require a verified NVIDIA GPU profile
# or: ./install.sh --gpu yes --mode online  # build/pull images instead of loading them
```

`--gpu yes` requires and validates the NVIDIA host and loaded CUDA image; it fails
instead of falling back to CPU. `--gpu no` installs CPU-only. `--mode` defaults to
`offline`; `--mode online` builds and pulls images via `accelerator.sh online` instead
of loading `images/runtime-images.tar`, and skips the offline firewall, client
credential, and boot-marker hardening. The chosen `cpu` or `gpu` profile is written to
`.env` and reused by all offline lifecycle commands. It is not re-detected after
installation.

Nginx binds to `0.0.0.0` on HTTP port 80 by default. Other computers connect directly
to the target address printed by the installer, for example `http://192.168.1.50`.
No DNS entry or CA certificate is required. Numbered, timestamped progress is shown on
screen and retained in `install.log`.

Optional installation environment variables:

```bash
SERVER_ADDRESS=192.168.1.50 ./install.sh --gpu no  # choose an assigned local address
LAN_CIDR=192.168.1.0/24 ./install.sh --gpu no      # override the trusted interface subnet
CLIENT_COUNT=3 ./install.sh --gpu no               # generate client-01 through client-03
HTTP_PORT=8080 ./install.sh --gpu no               # use a non-default host port
SSH_PORT=2222 ./install.sh --gpu no                # preserve a non-default LAN SSH port
BIND_ADDRESS=192.168.1.50 ./install.sh --gpu no    # restrict Nginx to one interface
```

`SERVER_ADDRESS` and a custom `BIND_ADDRESS` must be IPv4 addresses assigned to the
target. `LAN_CIDR` must contain `SERVER_ADDRESS`. `CLIENT_COUNT` accepts 1 through 99.

The installer performs these actions:

1. validates required files, commands, architecture, and installation state;
2. detects and validates the server address, interface, and trusted LAN CIDR;
3. checks four model filenames and their `models/SHA256SUMS` checksums, release checksums, free space, Docker, and the selected profile;
4. loads images, confirms CPU and CUDA image tags, and validates CUDA container access only for GPU;
5. force-removes containers identified by Chatbot BCA names or Compose labels and
   deletes their attached/orphaned volumes, while preserving unrelated Docker resources;
6. for GPU only, requires successful NVIDIA total-memory and process queries, warns
   and continues when total residual use is below 1024 MiB, and stops at 1024 MiB or more;
7. validates that the selected HTTP bind address/port is available;
8. creates `.env`, service passwords, persistent directories, and configured client keys
   (five by default);
9. starts and health-checks database, vector, and model services;
10. indexes local knowledge and reports progress for every configured figure;
11. enables LAN-only UFW rules and a persistent `DOCKER-USER` firewall service;
12. enables Docker at boot, starts Nginx/FastAPI, and calls authenticated readiness;
13. verifies every long-running chatbot container uses `restart: unless-stopped`.

After successful setup, `install.sh` writes `config/.installed` and refuses to run
again; use the lifecycle commands in section 9. A normal installation failure rolls
back generated chatbot containers, project volumes, secrets, and configuration. Legacy
chatbot containers and volumes are intentionally not restored, ensuring that a retry in
the same folder starts with a fresh PostgreSQL database. Docker images and model files
remain available, and fail-closed host firewall rules may remain active. If an abrupt
power loss leaves `.env` without the completion marker,
reset and retry with:

```bash
RESET_INCOMPLETE_INSTALL=YES ./install.sh
```

## 7. Generated secrets and client files

The default installation creates:

```text
config/auth/api_keys.json                 client IDs and token hashes
config/clients/client-01.txt              first API URL and plaintext credential
config/clients/client-02.txt              second API URL and plaintext credential
config/clients/client-03.txt              third API URL and plaintext credential
config/clients/client-04.txt              fourth API URL and plaintext credential
config/clients/client-05.txt              fifth API URL and plaintext credential
.env                                      canonical generated runtime configuration
install.log                               timestamped installation progress
```

Only one `config/clients/client-NN.txt` file should leave the target for its matching
computer. Never distribute `.env` or `config/auth/api_keys.json`.

Create, rotate, or remove later identities with the existing management command:

```bash
cd /home/superman/workspaces/chatbotbca
./scripts/offline/manage_client.sh add client-06
./scripts/offline/manage_client.sh remove client-06
```

A client cannot continue or delete another client's conversation. Cross-client
requests return HTTP 404 without revealing the owner.

## 8. LAN client setup

Give each client only its own credential file. On the client computer:

```bash
CHATBOT_URL=$(sed -n 's/^Chatbot URL: //p' client-01.txt)
CHATBOT_API_KEY=$(sed -n 's/^API key: //p' client-01.txt)
```

Public liveness:

```bash
curl "$CHATBOT_URL/api/v1/live"
```

Authenticated readiness:

```bash
curl -H "Authorization: Bearer $CHATBOT_API_KEY" \
  "$CHATBOT_URL/api/v1/ready"
```

Chat:

```bash
curl -H "Authorization: Bearer $CHATBOT_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Trong giám định ADN pháp y, STR được sử dụng như thế nào?"}' \
  "$CHATBOT_URL/api/v1/chat"
```

Streaming:

```bash
curl -N \
  -H "Authorization: Bearer $CHATBOT_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"Trong giám định ADN pháp y, mtDNA được sử dụng như thế nào?"}' \
  "$CHATBOT_URL/api/v1/chat/stream"
```

In Postman, set the target HTTP URL and add:

```text
Authorization: Bearer <client-api-key>
```

CORS affects browser frontends, not Postman or curl.

## 9. Normal target operation

Run from the extracted directory:

```bash
cd /home/superman/workspaces/chatbotbca

make status MODE=offline
make start MODE=offline
make index MODE=offline
make stop MODE=offline

# Parameterized operator actions remain explicit:
./scripts/offline/offline.sh logs chatbot
./scripts/offline/offline.sh logs llama-server
./scripts/offline/offline.sh backup
```

Restore is intentionally destructive and requires confirmation:

```bash
CONFIRM_RESTORE=YES \
  ./scripts/offline/offline.sh restore backups/<timestamp>
```

Backups stop client writes before taking a PostgreSQL snapshot and include
conversations, indexes, API-key hashes, and client credential files. They
do not replace the target's `.env` or PostgreSQL service password during restore.
Protect backup media physically.

The installer enables `docker.service`. PostgreSQL, ChromaDB, both model servers,
FastAPI, and Nginx use `restart: unless-stopped`, so they return automatically after a
normal reboot or power restoration. The indexer remains one-shot and is not rerun at
every boot. `make stop MODE=offline` intentionally removes the stack; run
`make start MODE=offline` to create it again.

## 10. LAN security

The proxy binds to `BIND_ADDRESS=0.0.0.0` by default. Reserve `SERVER_ADDRESS` in
DHCP so client URLs remain valid. HTTP traffic, prompts, answers, and API keys are
not encrypted; use this profile only on an isolated, trusted LAN. Do not configure
Internet port forwarding.

Installation preserves existing UFW rules, allows the selected LAN to HTTP and SSH,
sets default deny incoming/default allow outgoing, and enables UFW. Because Docker can
bypass ordinary UFW input rules, `chatbot-bca-firewall.service` reapplies an idempotent
`CHATBOT_BCA` chain under `DOCKER-USER` after Docker starts. The chain matches both the
configured original host HTTP port and Nginx's post-DNAT container port 80, so custom
host ports remain restricted without affecting unrelated Docker mappings. Inspect both
layers with:

```bash
sudo ufw status verbose
sudo iptables -L CHATBOT_BCA -n --line-numbers
sudo systemctl status chatbot-bca-firewall.service
```

Verify:

- an approved LAN client can connect;
- guest networks and untrusted VLANs cannot connect;
- the WAN cannot connect;
- only Nginx publishes the configured host HTTP port (80 by default).

## 11. Accelerator profiles

CPU installation sets all llama.cpp offload layers to `0` and needs no NVIDIA tools.
It has the same API and indexing behavior but requires substantially more time for
model startup, generation, and figure descriptions. Keep the conservative single
request slot until CPU capacity is measured on the target.

### GTX 1660 Super GPU profile

Initial settings in `.env`:

```text
LLAMA_CTX_SIZE=8192
LLAMA_BATCH_SIZE=512
LLAMA_UBATCH_SIZE=512
LLAMA_PARALLEL=1
LLAMA_GPU_LAYERS=16
LLAMA_GPU_LAYERS_DRAFT=0
EMBEDDING_CTX_SIZE=2048
EMBEDDING_BATCH_SIZE=2048
EMBEDDING_UBATCH_SIZE=2048
EMBEDDING_GPU_LAYERS=99
API_MAX_CONCURRENT_REQUESTS=1
API_QUEUE_TIMEOUT_SECONDS=900
```

Keep the LLM batch and micro-batch at 512 for multimodal image-token processing.
EmbeddingGemma requires a 2048-token context, batch, and micro-batch to classify and
retrieve against prompts of that length; lowering its micro-batch can cause classifier
and semantic-retrieval failures. This 16-layer profile was selected for the dedicated
6 GB target while retaining an 8192-token LLM context. If the target still reports CUDA
out-of-memory after the installer has removed legacy chatbot containers, first reduce
`LLAMA_CTX_SIZE=4096`. Keep one parallel generation slot until
target measurements show safe VRAM headroom. Requests
from five client computers may arrive together; they wait up to 15 minutes and are
processed one at a time to avoid exhausting the 6 GB GPU.

## 12. Troubleshooting

### Installer says a model is missing

Extract `models.zip` so the exact reported filename lands in:

```text
/home/superman/workspaces/chatbotbca/models
```

The installer verifies the four filenames and their `models/SHA256SUMS` checksums; it
does not download models.

### Installer stops during a long first index

Watch the numbered console output or `tail -f install.log`. Each configured figure
reports loading, reuse, generation, and immediate storage. A failed embedding/storage
request is retried three times for that figure without regenerating completed figures.
Initial multimodal descriptions can take several minutes each on a 6 GB GPU.

### Chatbot container is unhealthy

The installer prints chatbot and dependency logs before rollback. Legacy chatbot
volumes are removed before configuration, preventing an old PostgreSQL volume and new
password from being mixed. Correct the reported cause, then rerun in the same folder.

### Residual GPU processes are reported

Desktop processes such as Nautilus, Ptyxis, and GNOME Text Editor do not block
installation while NVIDIA reports less than 1024 MiB of total device memory in use.
At 1024 MiB or more, review the available PIDs with `ps` and `nvidia-smi`, stop the
substantial process safely, and rerun. A failed total-memory or process query also stops
installation; the installer never kills host processes or silently assumes that
measurement succeeded.

Only containers identified by supported Chatbot BCA names or Compose labels are
removed. Their Docker volumes are also deleted to prevent stale PostgreSQL credentials
from breaking API startup. Unrelated containers and volumes continue unchanged; Docker
images, GGUF models, and source files are preserved.

### HTTP 401

The client API key is missing, empty, rotated, or incorrect. In each new terminal,
reload it from the client's credential file.

### HTTP 429

The single generation slot remained busy for 15 minutes or the Nginx per-client rate
limit was reached. Wait and retry.

### HTTP 503 or classifier unavailable

Check:

```bash
make status MODE=offline
./scripts/offline/offline.sh logs embedding-server
./scripts/offline/offline.sh logs llama-server
./scripts/offline/offline.sh logs chatbot
```

The API becomes ready only after functional model, embedding, database, index, and
classifier warmup checks succeed.

### Missing image

Offline startup intentionally fails rather than pulling. Rebuild all three release
ZIPs on the preparation computer and transfer them again.

## 13. What the current Tailscale test proved

The current Ubuntu computer acted as the target and the MacBook acted as a remote
client. Tailscale and an SSH tunnel were only the temporary private-network path.
API-key authentication, readiness, generated chat, and streaming all worked.

At the target location, clients connect directly to the target's reserved LAN IPv4
address. Tailscale, SSH, DNS, and certificates are not required.

The real GTX 1660 Super target still requires final GPU-memory, direct-LAN,
firewall, reboot, and backup/restore tests.

## 14. Final acceptance checklist

With target WAN access disconnected:

- extract `chatbot_bca.zip`, `images.zip`, and `models.zip` under `/home/superman/workspaces`;
- reserve the target's LAN IPv4 address and confirm the installer selects its CIDR;
- run `./install.sh --gpu yes` (or `--gpu no`) successfully and confirm five credential files are generated;
- confirm legacy Chatbot BCA containers were removed, unrelated containers remain, and every new service is healthy;
- confirm authenticated `/api/v1/ready` reports `ready`;
- test prepared, generated, figure, streaming, and delete paths;
- verify invalid keys return HTTP 401;
- verify a second client cannot access the first client's conversation;
- check VRAM during generated and figure requests;
- verify UFW, `CHATBOT_BCA`, and `chatbot-bca-firewall.service` are active;
- reboot without Internet and confirm the API becomes ready without a manual start command;
- test backup and restore;
- confirm untrusted networks and WAN cannot reach the configured host HTTP port.
