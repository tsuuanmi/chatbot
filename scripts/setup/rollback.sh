# Rollback of generated state when an installation does not complete.

stop_incomplete_gpu_containers() {
  local container_id compose_project
  local existing_container_output
  existing_container_output="$(docker ps -q)"
  [[ -n "$existing_container_output" ]] || return 0
  while IFS= read -r container_id; do
    compose_project="$(docker inspect --format '{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{end}}' "$container_id")"
    if is_chatbot_project_identity "$compose_project"; then
      log "Stopping interrupted chatbot GPU container before residual GPU validation: $container_id"
      docker stop "$container_id" >/dev/null
      stopped_incomplete_gpu_containers+=("$container_id")
    fi
  done <<< "$existing_container_output"
}

cleanup_incomplete_installation() {
  local cleanup_status=0
  log "Removing generated state from the incomplete installation"
  if [[ -f "$INSTALL_DIR/.env" ]]; then
    export OFFLINE_ENV="$INSTALL_DIR/.env"
    # shellcheck source=../offline/common.sh
    source "$INSTALL_DIR/scripts/offline/common.sh"
    compose stop proxy chatbot chromadb >/dev/null 2>&1 || cleanup_status=1
    compose run --rm --no-deps --entrypoint bash chromadb \
      -c 'rm -rf /data/* /data/.[!.]* /data/..?*' \
      >/dev/null 2>&1 || cleanup_status=1
    compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=1
  fi
  if (( cleanup_status != 0 )); then
    log "Cleanup failed; retaining .env and credentials for operator recovery"
    return "$cleanup_status"
  fi
  rm -f "$INSTALL_DIR/.env" "$INSTALL_MARKER"
  rm -rf "$INSTALL_DIR/config/auth" "$INSTALL_DIR/config/clients" \
    "$INSTALL_DIR/config/tls"
  mkdir -p "$INSTALL_DIR/runtime/chromadb"
}

rollback_incomplete_installation() {
  local status=$?
  if (( status != 0 )) && (( ${#stopped_incomplete_gpu_containers[@]} > 0 )); then
    log "Restoring interrupted chatbot GPU containers after preflight failure"
    docker start "${stopped_incomplete_gpu_containers[@]}" >/dev/null \
      || log "Could not restore all interrupted chatbot GPU containers"
  fi
  if (( status != 0 )) && [[ "$installation_started" == true ]] \
    && [[ "$installation_complete" != true ]]; then
    log "Installation failed; rolling back generated chatbot state for a safe retry"
    if ! cleanup_incomplete_installation; then
      log "Automatic rollback was incomplete; preserve this folder for recovery"
    fi
    log "Removed selected chatbot containers and volumes are not restored; host firewall rules may remain active"
  fi
  return "$status"
}