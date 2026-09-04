# Rollback of generated state when an installation does not complete.

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