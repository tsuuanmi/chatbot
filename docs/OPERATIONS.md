# Operations

Run normal operational commands as the deployment user from the extracted runtime release directory.

Administrator privileges are required for installation and host configuration, but normal runtime operations do not require `sudo` when the deployment user has Docker access.

## Service Management

```bash
make status
make start
make stop
make restart
```

Follow all logs:

```bash
make logs
```

Follow one service:

```bash
make logs SERVICE=chatbot
```

Service names are `postgres`, `llama-server`, `chatbot`, and `proxy`.

## Health and Acceptance

Fast deployment verification:

```bash
make verify
```

Full target acceptance:

```bash
make accept
```

Use `make accept` after installation, a runtime upgrade, accelerator switching, or significant host changes.

## CPU and GPU

Switch to CPU:

```bash
make cpu
make verify
```

Switch to NVIDIA GPU:

```bash
make gpu
make verify
```

Switching accelerator does not change application semantics or rotate credentials.

## Knowledge Reindexing

```bash
make reindex
```

This rebuilds the approved document index using the existing PostgreSQL database.

## Configured Figures

Persistent configured figures live in:

```text
~/.local/share/chatbot/figures/
```

After adding, replacing, or removing configured figure files:

```bash
make reindex-figures
```

Figure descriptions are cached in PostgreSQL and reused when the original file bytes and description version have not changed.

## Code-Only Upgrade

When the required model bundle is already installed, only the new runtime ZIP is needed.

Extract the new runtime into a new directory:

```bash
unzip chatbot-<new-version>.zip
cd chatbot-<new-version>
sudo make install
```

The installer replaces the active `chatbot` runtime in place while preserving:

- model bundle
- figures
- API/authentication credentials
- PostgreSQL data volume

After the upgrade:

```bash
make status
make verify
make accept
```

## Model Upgrade

A new model ZIP is required only when the runtime manifest requires a different model bundle.

Place the required model ZIP beside the runtime directory and run:

```bash
sudo make install
```

The installer validates model names, manifests, and SHA256 checksums before activating the bundle.

## API Key

The persistent client API key is:

```text
~/.local/share/chatbot/state/secrets/chat_api_key
```

Do not copy it into source files, `.env`, shell history, logs, or documentation.

A normal release update must not change this key.

## Reboot Behavior

Docker and `chatbot-firewall.service` are enabled at boot. Runtime containers use `restart: unless-stopped`.

After a reboot, verification is:

```bash
systemctl is-active docker.service
systemctl is-active chatbot-firewall.service
make status
make verify
```

No manual `make start` should be necessary after a normal reboot.

## Troubleshooting

A `401 Unauthorized` from `/ready` or `/api/v1/*` usually means the Bearer API key is missing or invalid.

If GPU enablement fails, verify that Docker can access the NVIDIA device. CPU mode remains available with `make cpu`.

If another machine cannot access TCP/18080, confirm that its source address belongs to the LAN CIDR printed during installation. Tailscale/VPN addresses are not automatically included in the physical-LAN firewall rule.
