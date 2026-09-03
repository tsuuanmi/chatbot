# Offline Deployment and Operations

## 1. Delivery model

The final deliverable is three files created on an Internet-connected preparation
computer:

```text
/home/superman/workspaces/chatbot.zip   committed Git HEAD source and installer
/home/superman/workspaces/images.zip    exported Docker runtime images
/home/superman/workspaces/models.zip    the four GGUF model files with checksums
```

Extract all three ZIPs into the same parent directory only when it does not already
contain `chatbot/`. This prevents a previous release entrypoint from remaining after an
overlay extraction. Together they create a normal repository-like directory:

```text
chatbot/
├── src/                         application source
├── docs/                        operator and API documentation
├── config/                      static templates and generated secrets
├── scripts/setup.sh           canonical installer source
├── scripts/offline/             start, stop, client, backup, restore tools
├── data/                        packaged knowledge and configured figures
├── tests/                       source-level tests
├── images/runtime-images.tar    preloaded application and service images
├── models/                       the four GGUF model files extracted from models.zip
├── compose/                       Authoritative Compose definitions
│   ├── docker-compose.yml         online base profile
│   ├── docker-compose.gpu.yml     online GPU override
│   ├── docker-compose.offline.yml CPU-safe base profile
│   └── docker-compose.offline.gpu.yml offline GPU override
├── release-manifest.json
├── SHA256SUMS
└── setup.sh                   generated one-command target entry point
```

`chatbot.zip` contains source read from the committed `git archive HEAD`, plus
the generated release manifest, checksums, and root installer. The `compose/`
directory is the only authoritative location for Compose definitions; the installer
and lifecycle scripts select the needed base and optional GPU overlay directly, without
copying or generating a root Compose file. `images.zip` contains
only `chatbot/images/runtime-images.tar`. `models.zip` contains
`chatbot/models/` with the four GGUF files and a `SHA256SUMS` file. All three
ZIPs exclude Git metadata, secrets, virtual environments, caches, runtime databases,
and backups.

Extracting `models.zip` places these four files in `chatbot/models/`:

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

Supported target profiles:

- Ubuntu 22.04 LTS x86_64, Ubuntu 26.04 LTS x86_64, or Red Hat Enterprise Linux
  8.10 x86_64;
- Intel i7-9700K class CPU or better and 32 GB RAM;
- at least 20 GB free SSD space plus backup space, subject to final dual-image archive measurement;
- rootful Docker Engine with the Compose plugin that routes IPv4 `FORWARD` traffic
  first through its `DOCKER-USER` iptables chain; Podman and Docker firewall backends
  without that path are not supported;
- Ubuntu: UFW, iptables, systemd, and sudo access for automatic host security/startup setup;
- RHEL: firewalld, iptables, systemd, SELinux tools, and sudo access. SELinux must remain
  `Enforcing`; Compose applies the required labels to chatbot bind mounts;
- `unzip`, `openssl`, `curl`, Python 3.9 or newer as `python3`, `sha256sum`, `tar`,
  `ip`, `awk`, and `tee`;
- for GPU mode only: NVIDIA GTX 1660 Super 6 GB or better, NVIDIA driver, NVIDIA
  Container Toolkit, and `nvidia-smi`;
- a dedicated chatbot host: installation removes only containers and volumes with this
  release folder's path-derived Compose project label for a fresh database; resources
  from a previous naming scheme require the isolated migration command in section 6.1.
  Unrelated containers and volumes, Docker images, GGUF models, and source files are
  preserved;
- a reserved/static LAN IPv4 address is recommended so client URLs remain stable.

Check before transfer:

```bash
docker version
docker compose version
python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version'

# RHEL 8.10 only
getenforce
firewall-cmd --state

# GPU mode only
nvidia-smi
docker info --format '{{json .Runtimes}}'
```

GPU mode requires `nvidia` in the final Docker-runtime output. CPU mode has no NVIDIA
host requirement.

## 4. Create the release ZIPs

On the preparation computer:

```bash
cd /home/superman/workspaces/chatbot
make prepare
```

The builder:

1. refuses modified, deleted, staged, or untracked working-tree files;
2. exports the exact committed source with `git archive HEAD`;
3. pulls third-party images pinned by digest;
4. builds the Chatbot application image from that committed source;
5. exports all runtime images to `images/runtime-images.tar`;
6. records the source commit and required image tags in `release-manifest.json`;
7. creates `SHA256SUMS` for source/configuration files and a separate
   `models/SHA256SUMS` for the GGUF files; `release-manifest.json` records the
   SHA-256 checksum of `images/runtime-images.tar` and is itself source-checksummed;
8. creates and integrity-checks all three ZIPs before publishing them, and removes
   already-published outputs if publishing a later one fails.

Commit and review every intended change before running `make prepare`. There is no
dirty-tree override because `chatbot.zip` must identify one exact Git commit.
Remove all three old outputs before rebuilding:

```bash
rm -f /home/superman/workspaces/chatbot.zip \
      /home/superman/workspaces/images.zip \
      /home/superman/workspaces/models.zip
make prepare
```

## 5. Transfer and extract

Use exFAT or ext4 media, not FAT32. Copy `chatbot.zip`, `images.zip`, and
`models.zip`.

On the target, extract all three ZIPs from the same parent directory so they merge
into one `chatbot/` folder:

```bash
mkdir -p /home/superman/workspaces
test ! -e /home/superman/workspaces/chatbot || {
  echo "Refusing to overlay an existing chatbot directory." >&2
  exit 1
}
cd /home/superman/workspaces
unzip /media/$USER/<USB>/chatbot.zip
unzip /media/$USER/<USB>/images.zip
unzip /media/$USER/<USB>/models.zip
cd chatbot
```

The result should be:

```text
/home/superman/workspaces/chatbot
```

The four GGUF model files and their `SHA256SUMS` are placed in:

```text
/home/superman/workspaces/chatbot/models
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
cd /home/superman/workspaces/chatbot
chmod +x setup.sh
./setup.sh --gpu no             # CPU profile, no NVIDIA requirement
# or: ./setup.sh --gpu yes      # require a verified NVIDIA GPU profile
# or: ./setup.sh --gpu yes --mode online  # build/pull images instead of loading them
```

`./setup.sh` is the offline release entrypoint; `make setup` remains the development
dependency setup command. `--gpu yes` requires and validates a 6 GiB NVIDIA GPU, the
NVIDIA host, and the loaded CUDA image; it fails instead of falling back to CPU. `--gpu no` installs CPU-only.
`--mode` defaults to
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
SERVER_ADDRESS=192.168.1.50 ./setup.sh --gpu no  # choose an assigned local address
LAN_CIDR=192.168.1.0/24 ./setup.sh --gpu no      # override the trusted interface subnet
CLIENT_COUNT=3 ./setup.sh --gpu no               # generate client-01 through client-03
HTTP_PORT=8080 ./setup.sh --gpu no               # use a non-default host port
SSH_PORT=2222 ./setup.sh --gpu no                # preserve a non-default LAN SSH port
BIND_ADDRESS=192.168.1.50 ./setup.sh --gpu no    # restrict Nginx to one interface
```

`SERVER_ADDRESS` and a custom `BIND_ADDRESS` must be IPv4 addresses assigned to the
target. `LAN_CIDR` must contain `SERVER_ADDRESS`. `CLIENT_COUNT` accepts 1 through 99.

The installer performs these actions:

1. validates required files, commands, architecture, and installation state;
2. detects and validates the server address, interface, and trusted LAN CIDR;
3. checks four model filenames and their `models/SHA256SUMS` checksums, release checksums, the manifest-recorded runtime image archive checksum, free space, Docker, and the selected profile;
4. loads images only after the archive checksum passes, confirms CPU and CUDA image tags, and validates CUDA container access and at least 6 GiB on every NVIDIA GPU before cleanup;
5. preflights the selected host firewall backend, SELinux on RHEL, conntrack support,
   and Docker's `DOCKER-USER` chain before deleting current chatbot data;
6. for GPU only, requires successful NVIDIA total-memory and process queries, warns
   and continues when total residual use is below 1024 MiB, and stops at 1024 MiB or more;
7. validates that the selected HTTP bind address/port is available;
8. force-removes only containers and volumes carrying this release folder's
   path-derived Compose project label, while preserving unrelated Docker resources;
9. creates `.env`, service passwords, persistent directories, and configured client keys
   (five by default);
10. starts and health-checks database, vector, and model services;
11. indexes local knowledge and reports progress for every configured figure;
12. enables LAN-only UFW rules on Ubuntu or permanent firewalld rules on RHEL, plus a
    persistent `DOCKER-USER` firewall service;
13. enables Docker at boot, starts Nginx/FastAPI, and calls authenticated readiness;
14. verifies every long-running chatbot container uses `restart: unless-stopped`.

After successful setup, `setup.sh` writes `config/.installed` and refuses to run
again; use the lifecycle commands in section 9. A normal installation failure rolls
back generated chatbot containers, project volumes, secrets, and configuration. Selected
chatbot containers and volumes are intentionally not restored, ensuring that a retry in
the same folder starts with a fresh PostgreSQL database. Docker images and model files
remain available, and fail-closed host firewall rules may remain active. The installer
records its intended firewall state before changing host rules, so
`RESET_INCOMPLETE_INSTALL=YES` reconciles those rules on retry. The installer verifies
Docker's `DOCKER-USER` chain before selected chatbot data is removed and rechecks it after
backend containers start; if that final check fails, selected chatbot data is still not
restored. If an abrupt power loss leaves `.env` without the completion marker,
reset and retry with:

```bash
RESET_INCOMPLETE_INSTALL=YES ./setup.sh --gpu no
```

### 6.1. Migrate resources from an earlier naming scheme

The chatbot-only release does not guess or automatically delete resources from an
older naming scheme. Before reusing a host, list the exact containers and volumes that
belong to the previous deployment, review the list, and pass only those resources to
the isolated migration command:

```bash
docker ps -a --format '{{.Names}}'
docker volume ls -q
./scripts/offline/migrate_resources.sh --confirm \
  --container <previous-container-name-or-id> \
  --volume <previous-volume-name>
```

Repeat the `--container` and `--volume` options as needed. The command is not called by
`setup.sh`, accepts no wildcards, and requires `--confirm`. Handle any previous host
firewall unit, program, state file, or iptables chain separately with the host's
administration tools before enabling the new chatbot firewall service.

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
cd /home/superman/workspaces/chatbot
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
cd /home/superman/workspaces/chatbot

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

Ubuntu installation preserves existing UFW rules, allows the selected LAN to HTTP and SSH,
sets default deny incoming/default allow outgoing, and enables UFW. RHEL installation
removes generic SSH service and selected-port allowances from the selected firewalld zone,
then replaces them with source-restricted rich rules. It does not reset firewalld or alter
unrelated zones. Its preflight rejects broad accepting rich rules for the selected SSH or
HTTP ports. RHEL requires SELinux `Enforcing`; the Compose `:z` and `:Z` bind-mount labels
grant containers only the necessary access.

Because Docker can bypass host firewall input rules, `chatbot-firewall.service`
reapplies an idempotent `CHATBOT` chain under `DOCKER-USER` after Docker starts. The
chain matches both the configured original host HTTP port and Nginx's post-DNAT container
port 80, so custom host ports remain restricted without affecting unrelated Docker
mappings. Inspect the active host firewall, Docker chain, and boot unit with:

```bash
# Ubuntu
sudo ufw status verbose

# RHEL
getenforce
sudo firewall-cmd --list-all-zones

# Both targets
sudo iptables -L CHATBOT -n --line-numbers
sudo systemctl status chatbot-firewall.service
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
out-of-memory after the installer has removed selected chatbot containers, first reduce
`LLAMA_CTX_SIZE=4096`. Keep one parallel generation slot until
target measurements show safe VRAM headroom. Requests
from five client computers may arrive together; they wait up to 15 minutes and are
processed one at a time to avoid exhausting the 6 GB GPU.

## 12. Troubleshooting

### Installer says a model is missing

Extract `models.zip` so the exact reported filename lands in:

```text
/home/superman/workspaces/chatbot/models
```

The installer verifies the four filenames and their `models/SHA256SUMS` checksums; it
does not download models.

### Installer stops during a long first index

Watch the numbered console output or `tail -f install.log`. Each configured figure
reports loading, reuse, generation, and immediate storage. A failed embedding/storage
request is retried three times for that figure without regenerating completed figures.
Initial multimodal descriptions can take several minutes each on a 6 GB GPU.

### Chatbot container is unhealthy

The installer prints chatbot and dependency logs before rollback. Selected chatbot
volumes are removed before configuration, preventing an old PostgreSQL volume and new
password from being mixed. Resources from an earlier naming scheme are not selected;
use section 6.1 when a manual migration is needed. Correct the reported cause, then
rerun in the same folder. On
RHEL, keep SELinux
`Enforcing`; inspect recent denials with `sudo ausearch -m AVC -ts recent` rather than
disabling it.

### Residual GPU processes are reported

Desktop processes such as Nautilus, Ptyxis, and GNOME Text Editor do not block
installation while NVIDIA reports less than 1024 MiB of total device memory in use.
At 1024 MiB or more, review the available PIDs with `ps` and `nvidia-smi`, stop the
substantial process safely, and rerun. A failed total-memory or process query also stops
installation; the installer never kills host processes or silently assumes that
measurement succeeded.

Only containers and volumes with this release folder's path-derived Compose project
label are removed to prevent stale PostgreSQL credentials from breaking API startup.
Unrelated containers and volumes continue unchanged; Docker
images, GGUF models, and source files are preserved. Resources from an earlier naming
scheme require the explicit, isolated migration command in section 6.1.

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

- extract `chatbot.zip`, `images.zip`, and `models.zip` under `/home/superman/workspaces`;
- reserve the target's LAN IPv4 address and confirm the installer selects its CIDR;
- run `./setup.sh --gpu yes` (or `--gpu no`) successfully and confirm five credential files are generated;
- confirm only containers and volumes with the release folder's project label were removed, unrelated resources remain, and every new service is healthy; migrate any earlier-naming resources separately;
- confirm authenticated `/api/v1/ready` reports `ready`;
- test prepared, generated, figure, streaming, and delete paths;
- verify invalid keys return HTTP 401;
- verify a second client cannot access the first client's conversation;
- check VRAM during generated and figure requests;
- verify UFW on Ubuntu or firewalld plus SELinux `Enforcing` on RHEL, then verify
  `CHATBOT` and `chatbot-firewall.service` are active;
- reboot without Internet and confirm the API becomes ready without a manual start command;
- test backup and restore;
- confirm untrusted networks and WAN cannot reach the configured host HTTP port.
