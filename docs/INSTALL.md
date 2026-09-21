# Installation

This guide describes the validated Ubuntu offline deployment workflow.

## Prerequisites

The target host must already provide:

- Docker Engine
- Docker Compose plugin
- Python 3
- GNU make
- unzip

For NVIDIA acceleration, the host must also have a working NVIDIA driver and Docker GPU integration. GPU support is optional.

The target does not need Internet access during Chatbot installation.

## Required Artifacts

For a fresh installation copy these files to the target:

```text
chatbot-<version>.zip
chatbot-models-gemma4-e2b-v2.zip
```

Keep the model ZIP compressed. The installer reads it directly.

Recommended layout:

```text
release/
├── chatbot-<version>/
└── chatbot-models-gemma4-e2b-v2.zip
```

Create that layout with:

```bash
unzip chatbot-<version>.zip
cd chatbot-<version>
```

## Install

Run:

```bash
sudo make install
```

`sudo` is intentional. Host setup requires administrator access for Docker boot configuration, systemd, and firewall rules. The installer still treats the user who invoked `sudo` as the deployment owner.

Persistent files therefore remain owned by the deployment user rather than root.

A successful installation ends with output similar to:

```text
OFFLINE VERIFY PASS
OFFLINE INSTALL PASS
accelerator=gpu
local=http://127.0.0.1:18080
network=http://192.168.1.208:18080
project=chatbot
```

The selected accelerator may be `cpu` instead.

## Accelerator Selection

Automatic selection is the default:

```bash
sudo make install
```

Force CPU during installation:

```bash
sudo make install ACCELERATOR=cpu
```

Force NVIDIA GPU:

```bash
sudo make install ACCELERATOR=gpu
```

Forced GPU mode fails rather than silently using CPU if Docker cannot expose a CUDA device.

## Persistent State

Default locations:

```text
~/.local/share/chatbot/models/
~/.local/share/chatbot/figures/
~/.local/share/chatbot/state/secrets/
```

PostgreSQL uses:

```text
chatbot_postgres_data
```

The secret store contains:

```text
chat_api_key
chat_auth.json
llama_api_key
postgres_password
```

The installer reuses the complete secret set. It refuses partial secret state instead of generating a mixture of old and new credentials.

The client API key is stable across code releases, installer reruns, CPU/GPU switching, Docker restarts, and host reboots as long as the persistent state directory is preserved.

## Network and Firewall

The production Nginx gateway publishes host TCP port `18080`.

The installer detects the primary LAN IPv4 address and subnet and installs a persistent Docker `DOCKER-USER` firewall rule. Only the detected LAN subnet is allowed to reach the Chatbot published port.

For example:

```text
host=192.168.1.208
LAN=192.168.1.0/24
gateway=TCP/18080
```

A Tailscale address such as `100.x.x.x` is not automatically treated as part of the physical LAN.

HTTP traffic is not encrypted. Use the default LAN exposure only on a trusted or isolated network.

## Boot Behavior

The installer enables Docker at boot and installs a persistent `chatbot-firewall.service`.

The four runtime containers use `restart: unless-stopped`, so they return automatically when Docker starts after a reboot.

## Verification

Run as the normal deployment user after installation:

```bash
make status
make verify
make accept
```

`make accept` validates runtime security, container health, Docker boot enablement, restart policies, persistent LAN firewall configuration, media behavior, and the public platform contract.

## First API Test

```bash
curl -i http://127.0.0.1:18080/live
```

Expected status: `200 OK`.

Readiness requires authentication:

```bash
API_KEY="$(cat "$HOME/.local/share/chatbot/state/secrets/chat_api_key")"

curl -i \
  -H "Authorization: Bearer $API_KEY" \
  http://127.0.0.1:18080/ready
```

Expected status: `200 OK`.
