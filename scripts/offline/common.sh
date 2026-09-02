#!/usr/bin/env bash
set -Eeuo pipefail

OFFLINE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OFFLINE_ENV="${OFFLINE_ENV:-$OFFLINE_ROOT/.env}"
OFFLINE_COMPOSE="$OFFLINE_ROOT/compose/docker-compose.offline.yml"
OFFLINE_GPU_COMPOSE="$OFFLINE_ROOT/compose/docker-compose.offline.gpu.yml"
# shellcheck source=../accelerator.sh
source "$OFFLINE_ROOT/scripts/accelerator.sh"
project_digest="$(printf '%s' "$OFFLINE_ROOT" | sha256sum)"
project_digest="${project_digest%% *}"
OFFLINE_PROJECT_NAME="chatbot-bca-${project_digest:0:12}"

offline_log() {
  printf '[offline %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required command not found: $1" >&2
    exit 1
  }
}

require_installation() {
  [[ -f "$OFFLINE_ENV" ]] || {
    echo "Offline installation is not configured: $OFFLINE_ENV" >&2
    exit 1
  }
}

offline_accelerator() {
  local accelerator
  accelerator="$(awk -F= '$1 == "ACCELERATOR" { print substr($0, index($0, "=") + 1) }' "$OFFLINE_ENV")"
  [[ "$accelerator" == "cpu" || "$accelerator" == "gpu" ]] || {
    echo "Offline accelerator is invalid or missing from $OFFLINE_ENV" >&2
    exit 1
  }
  printf '%s\n' "$accelerator"
}

compose() {
  local accelerator
  accelerator="$(offline_accelerator)"
  accelerator_compose_files "$accelerator" "$OFFLINE_COMPOSE" "$OFFLINE_GPU_COMPOSE"
  docker compose --project-directory "$OFFLINE_ROOT" \
    --project-name "$OFFLINE_PROJECT_NAME" --env-file "$OFFLINE_ENV" \
    "${ACCELERATOR_COMPOSE_FILES[@]}" "$@"
}

run_indexer() {
  local attempts="${1:-3}"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    offline_log "Starting indexer attempt $attempt/$attempts"
    if compose run --rm --no-deps indexer; then
      offline_log "Indexer completed successfully on attempt $attempt/$attempts"
      return 0
    fi
    offline_log "Indexer attempt $attempt/$attempts failed"
    if (( attempt < attempts )); then
      offline_log "Waiting 5 seconds before retrying the indexer"
      sleep 5
    fi
  done
  return 1
}

wait_for_service() {
  local service="$1"
  local attempts="${2:-60}"
  local container_id status="not-created"
  offline_log "Waiting up to $((attempts * 2)) seconds for service: $service"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    container_id="$(compose ps -q "$service")"
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || printf 'inspect-failed')"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        offline_log "Service $service is $status after $((attempt * 2)) seconds"
        return 0
      fi
    fi
    if (( attempt == 1 || attempt % 5 == 0 )); then
      offline_log "Service $service status after $((attempt * 2)) seconds: $status"
    fi
    sleep 2
  done
  echo "Service did not become ready: $service (last status: $status)" >&2
  compose logs --tail=100 "$service" >&2 || true
  return 1
}

wait_for_backend_services() {
  wait_for_service postgres 90
  wait_for_service chromadb 90
  wait_for_service llama-server 210
  wait_for_service embedding-server 180
}
