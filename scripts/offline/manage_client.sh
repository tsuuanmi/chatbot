#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
require_installation
require_command awk
require_command python3

ACTION="${1:-}"
CLIENT_ID="${2:-}"
KEY_FILE="$OFFLINE_ROOT/config/auth/api_keys.json"
CLIENT_DIR="$OFFLINE_ROOT/config/clients"
SERVER_ADDRESS="$(awk -F= '$1 == "SERVER_ADDRESS" { print substr($0, index($0, "=") + 1) }' "$OFFLINE_ENV")"
HTTP_PORT="$(awk -F= '$1 == "HTTP_PORT" { print substr($0, index($0, "=") + 1) }' "$OFFLINE_ENV")"
[[ -n "$SERVER_ADDRESS" && -n "$HTTP_PORT" ]] || {
  echo "Offline HTTP address is missing from $OFFLINE_ENV" >&2
  exit 1
}
if [[ "$HTTP_PORT" == "80" ]]; then
  CLIENT_URL="http://$SERVER_ADDRESS"
else
  CLIENT_URL="http://$SERVER_ADDRESS:$HTTP_PORT"
fi
[[ "$ACTION" == "add" || "$ACTION" == "remove" ]] \
  && [[ "$CLIENT_ID" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{1,63}$ ]] || {
  echo "usage: $0 {add|remove} CLIENT_ID" >&2
  exit 2
}

python3 - "$ACTION" "$KEY_FILE" "$CLIENT_DIR" "$CLIENT_ID" \
  "$CLIENT_URL" <<'PY'
import fcntl
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path


def atomic_write(path: Path, content: str, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def token_from_credential(path: Path) -> str | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("API key: "):
                return line.removeprefix("API key: ")
    except OSError:
        return None
    return None


action = sys.argv[1]
key_path = Path(sys.argv[2])
client_dir = Path(sys.argv[3])
client_id = sys.argv[4]
client_url = sys.argv[5]
client_dir.mkdir(parents=True, exist_ok=True)
credential_path = client_dir / f"{client_id}.txt"
pending_path = client_dir / f"{client_id}.pending.txt"
lock_path = key_path.with_name(".api_keys.lock")

with lock_path.open("a+", encoding="utf-8") as lock:
    os.chmod(lock_path, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    payload = json.loads(key_path.read_text(encoding="utf-8"))
    clients = {item["id"]: item["token_sha256"] for item in payload["clients"]}

    pending_token = token_from_credential(pending_path)
    if pending_token is not None and clients.get(client_id) == hashlib.sha256(
        pending_token.encode("utf-8")
    ).hexdigest():
        os.replace(pending_path, credential_path)

    if action == "add":
        token = secrets.token_urlsafe(36)
        clients[client_id] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        credential = (
            f"Chatbot URL: {client_url}\n"
            f"Client ID: {client_id}\n"
            f"API key: {token}\n"
        )
        atomic_write(pending_path, credential, 0o600)
        updated = {
            "version": 1,
            "clients": [
                {"id": item_id, "token_sha256": token_hash}
                for item_id, token_hash in sorted(clients.items())
            ],
        }
        atomic_write(key_path, json.dumps(updated, indent=2) + "\n", 0o640)
        os.replace(pending_path, credential_path)
        print(f"Created/rotated client: {client_id}")
        print(f"Credentials: {credential_path}")
    else:
        clients.pop(client_id, None)
        if not clients:
            raise SystemExit("refusing to remove the final API client")
        updated = {
            "version": 1,
            "clients": [
                {"id": item_id, "token_sha256": token_hash}
                for item_id, token_hash in sorted(clients.items())
            ],
        }
        atomic_write(key_path, json.dumps(updated, indent=2) + "\n", 0o640)
        credential_path.unlink(missing_ok=True)
        pending_path.unlink(missing_ok=True)
        print(f"Removed client: {client_id}")
PY
