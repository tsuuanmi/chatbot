#!/usr/bin/env bash
set -Eeuo pipefail

# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
require_installation
require_command docker

start_stack() {
  offline_log "Starting database, vector, and model services"
  compose up -d --no-build --pull never postgres chromadb llama-server embedding-server
  wait_for_backend_services
  offline_log "Starting chatbot API and Nginx gateway"
  compose up -d --no-build --pull never chatbot proxy
  wait_for_service chatbot 60
  wait_for_service proxy 30
  offline_log "Offline chatbot stack is ready"
  compose ps
}

reindex_stack() {
  offline_log "Stopping client-facing services before reindexing"
  compose stop proxy chatbot || true
  offline_log "Starting required backend services"
  compose up -d --no-build --pull never postgres chromadb llama-server embedding-server
  wait_for_backend_services
  run_indexer 3
  offline_log "Restarting client-facing services"
  compose up -d --no-build --pull never chatbot proxy
  wait_for_service chatbot 60
  wait_for_service proxy 30
  offline_log "Reindex completed and client access is restored"
}

backup_stack() {
  local timestamp destination backup_status=0 restart_status=0
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="$OFFLINE_ROOT/backups/$timestamp"
  mkdir -p "$destination"
  (
    set -Eeuo pipefail
    compose stop proxy chatbot
    compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
      > "$destination/postgres.sql"
    compose stop chromadb
    tar -C "$OFFLINE_ROOT" -czf "$destination/chromadb.tar.gz" runtime/chromadb
    tar -C "$OFFLINE_ROOT" -czf "$destination/config.tar.gz" \
      config/auth config/clients
    cd "$destination"
    sha256sum postgres.sql chromadb.tar.gz config.tar.gz > SHA256SUMS
    chmod -R go-rwx .
  ) || backup_status=$?

  compose up -d --no-build --pull never chromadb chatbot proxy \
    || restart_status=$?
  if (( restart_status == 0 )); then
    wait_for_service chromadb 30 || restart_status=$?
    wait_for_service chatbot 60 || restart_status=$?
    wait_for_service proxy 30 || restart_status=$?
  fi
  if (( backup_status != 0 )); then
    rm -rf "$destination"
    echo "Backup failed; partial output was removed." >&2
    return "$backup_status"
  fi
  if (( restart_status != 0 )); then
    echo "Backup completed, but services did not restart cleanly." >&2
    return "$restart_status"
  fi
  echo "Backup created: $destination"
  echo "This backup contains API credentials and secrets; protect it physically."
}

restore_stack() {
  local source="$1"
  [[ "${CONFIRM_RESTORE:-}" == "YES" ]] || {
    echo "Restore replaces current conversations, indexes, and secrets." >&2
    echo "Re-run with CONFIRM_RESTORE=YES after verifying the backup path." >&2
    exit 1
  }
  [[ -f "$source/SHA256SUMS" ]] || { echo "Invalid backup: $source" >&2; exit 1; }
  (cd "$source" && sha256sum -c SHA256SUMS)
  compose down
  compose run --rm --no-deps --entrypoint bash chromadb \
    -c 'rm -rf /data/* /data/.[!.]* /data/..?*'
  tar -C "$OFFLINE_ROOT" -xzf "$source/chromadb.tar.gz"
  rm -rf "$OFFLINE_ROOT/config/auth" "$OFFLINE_ROOT/config/clients" \
    "$OFFLINE_ROOT/config/tls"
  tar -C "$OFFLINE_ROOT" -xzf "$source/config.tar.gz"
  compose up -d --no-build --pull never postgres chromadb llama-server embedding-server
  wait_for_service postgres 30
  compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
  compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"' < "$source/postgres.sql"
  start_stack
  echo "Backup restored: $source"
}

case "${1:-}" in
  start) start_stack ;;
  stop) compose down ;;
  status) compose ps ;;
  logs) compose logs --tail="${TAIL:-200}" -f "${2:-chatbot}" ;;
  reindex) reindex_stack ;;
  backup) backup_stack ;;
  restore)
    [[ -n "${2:-}" ]] || { echo "usage: $0 restore BACKUP_DIRECTORY" >&2; exit 2; }
    restore_stack "$2"
    ;;
  *)
    echo "usage: $0 {start|stop|status|logs [service]|reindex|backup|restore DIR}" >&2
    exit 2
    ;;
esac
