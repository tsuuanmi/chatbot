# Shared primitives used by setup.sh and its step modules.

log() {
  printf '[install %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

is_chatbot_project_identity() {
  local identity="$1"
  [[ "$identity" == "$CHATBOT_PROJECT_NAME" ]]
}

add_chatbot_volume() {
  local candidate="$1" existing_volume
  for existing_volume in "${chatbot_volumes[@]}"; do
    [[ "$candidate" == "$existing_volume" ]] && return 0
  done
  chatbot_volumes+=("$candidate")
}

print_startup_diagnostics() {
  log "Service startup failed; printing status and diagnostic logs before rollback"
  compose ps >&2 || true
  compose logs --tail=200 \
    postgres chromadb llama-server embedding-server chatbot proxy >&2 || true
}

step() {
  step_number=$((step_number + 1))
  current_step="$*"
  log "STEP $step_number/$total_steps: $current_step"
}

report_error() {
  local status=$?
  log "ERROR during '$current_step' at line ${BASH_LINENO[0]}: $BASH_COMMAND"
  return "$status"
}

usage() {
  echo "usage: $0 [--gpu yes|no] [--mode offline|online] [--reinstall] [--zip-dir DIR]" >&2
  echo "--gpu defaults to yes: the verified NVIDIA GPU profile; --gpu no installs CPU-only." >&2
  echo "optional environment: SERVER_ADDRESS, LAN_CIDR, BIND_ADDRESS, HTTP_PORT, SSH_PORT, CLIENT_COUNT, ZIP_DIR" >&2
}