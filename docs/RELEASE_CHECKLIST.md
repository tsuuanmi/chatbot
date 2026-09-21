# Release Acceptance Checklist

This checklist describes the current universal offline release.

CPU support is required. NVIDIA GPU acceleration is optional and must not change application behavior.

## Source Gate

Before creating a runtime artifact:

```bash
make test
make verify
make accept
make recovery
git diff --check
git status --short
```

Build a release only from a clean committed HEAD.

## Runtime Artifact

```bash
make release
```

Artifact:

```text
chatbot-<version>.zip
```

It contains the application, CPU llama.cpp image, NVIDIA llama.cpp image, PostgreSQL image, Nginx image, Compose files, migrations, approved data, offline tooling, checksums, and release manifest.

It must not contain private secrets, PostgreSQL data, or GGUF model files.

Verify:

```bash
python3 -m tools.release verify runtime dist/chatbot-<version>.zip
```

## Model Artifact

Rebuild only when the model contract changes:

```bash
make release-models
```

Current model bundle contains:

- main Gemma GGUF
- multimodal projector GGUF
- Gemma MTP draft GGUF
- model manifest
- SHA256 checksums

Artifact:

```text
chatbot-models-gemma4-e2b-v2.zip
```

## Fresh Target Install

Place the runtime ZIP and model ZIP together, extract the runtime ZIP, then:

```bash
sudo make install
```

Required result:

- all five Docker images load without network pulls
- correct model package installs or is reused
- accelerator auto-selection succeeds
- persistent credentials initialize or are reused
- database migrations succeed
- 105 approved documents are indexed
- configured figure cache succeeds
- exactly four long-running services become healthy
- Docker boot startup is enabled
- persistent LAN firewall is installed
- `OFFLINE VERIFY PASS`
- `OFFLINE INSTALL PASS`

After installation, `.env` and persistent deployment state must remain accessible to the deployment user rather than being owned exclusively by root.

## Persistent State Gate

Runtime upgrades must preserve:

- `~/.local/share/chatbot/models/`
- `~/.local/share/chatbot/figures/`
- `~/.local/share/chatbot/state/secrets/`
- `chatbot_postgres_data`

The client API key must remain byte-identical across normal runtime upgrades, CPU/GPU switching, Docker restart, and host reboot.

## Target Acceptance

```bash
make status
make verify
make accept
```

Acceptance must verify four healthy services, non-root/read-only runtime hardening, private internal boundaries, Docker boot enablement, `restart: unless-stopped`, persistent LAN firewall configuration, media behavior, and the public API.

## Public API Gate

Required production behavior:

- `/live` returns 200 without authentication
- `/ready` returns 401 without authentication
- authenticated `/ready` returns 200
- authenticated `/api/v1/chat` returns the direct public DTO
- streaming works through `/api/v1/chat/stream`
- conversation deletion uses UUID ownership
- internal Hayhooks/runtime-management endpoints return 404 through Nginx

## Restart / Reboot Gate

Docker restart acceptance must demonstrate that no manual `make start` is required:

```bash
sudo systemctl restart docker.service
```

Required after Docker returns:

- all four Chatbot containers automatically become healthy
- `chatbot-firewall.service` is active
- `DOCKER-USER` contains the Chatbot firewall jump
- LAN allow/drop rules are restored
- `make verify` passes
- `make accept` passes
- API key hash is unchanged

## Network Gate

The validated default gateway is TCP/18080 on the detected LAN address.

The persistent firewall allows the detected physical LAN CIDR and drops other source networks for the Chatbot published port.

VPN or Tailscale networks are not automatically included in that LAN policy.

## Ubuntu Release Status

Ubuntu x86_64 release acceptance is COMPLETE, including fresh/upgrade installation, CPU/GPU parity, multimodal behavior, persistent credentials, public API, LAN firewall, Docker restart recovery, and stable API key.

## RHEL / SELinux

Real RHEL-compatible host validation with SELinux Enforcing is future work.

It must not be represented as completed until tested on a real host, and SELinux must not be disabled as a workaround.
