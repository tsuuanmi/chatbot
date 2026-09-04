# Deployment steps: resource removal, configuration, services, and readiness.

remove_existing_chatbot_resources() {
  local container_id container_name compose_project container_volume_output volume volume_project
  local existing_container_output existing_volume_output
  local -a existing_containers=() chatbot_containers=() chatbot_volumes=() existing_volumes=()
  existing_container_output="$(docker ps -aq)"
  if [[ -n "$existing_container_output" ]]; then
    mapfile -t existing_containers <<< "$existing_container_output"
  fi
  if (( ${#existing_containers[@]} == 0 )); then
    log "No pre-existing Docker containers found"
  else
    for container_id in "${existing_containers[@]}"; do
      container_name="$(docker inspect --format '{{.Name}}' "$container_id")"
      container_name="${container_name#/}"
      compose_project="$(docker inspect --format '{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{end}}' "$container_id")"
      if is_chatbot_project_identity "$compose_project"; then
        chatbot_containers+=("$container_id")
        container_volume_output="$(docker inspect --format '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}' "$container_id")"
        if [[ -n "$container_volume_output" ]]; then
          while IFS= read -r volume; do
            add_chatbot_volume "$volume"
          done <<< "$container_volume_output"
        fi
        log "Selected chatbot container for removal: $container_name ($container_id)"
      else
        log "Preserving unrelated container: $container_name ($container_id)"
      fi
    done
  fi

  existing_volume_output="$(docker volume ls -q)"
  if [[ -n "$existing_volume_output" ]]; then
    mapfile -t existing_volumes <<< "$existing_volume_output"
  fi
  for volume in "${existing_volumes[@]}"; do
    volume_project="$(docker volume inspect --format '{{if .Labels}}{{index .Labels "com.docker.compose.project"}}{{end}}' "$volume")"
    if is_chatbot_project_identity "$volume_project"; then
      add_chatbot_volume "$volume"
    fi
  done

  if (( ${#chatbot_containers[@]} > 0 )); then
    log "Force-removing ${#chatbot_containers[@]} chatbot container(s)"
    docker rm -f "${chatbot_containers[@]}" >/dev/null
  else
    log "No existing chatbot containers matched this deployment's Compose project label"
  fi
  if (( ${#chatbot_volumes[@]} > 0 )); then
    log "Removing ${#chatbot_volumes[@]} chatbot Docker volume(s) for a fresh installation"
    docker volume rm "${chatbot_volumes[@]}" >/dev/null
  else
    log "No existing chatbot Docker volumes matched"
  fi
  rm -f "$INSTALL_DIR/config/.protected-volumes"
}

generate_runtime_configuration() {
  local llama_key embedding_key postgres_password app_image
  local llama_gpu_layers llama_gpu_layers_draft embedding_gpu_layers
  mkdir -p "$INSTALL_DIR/runtime/chromadb" "$INSTALL_DIR/config/auth" \
    "$INSTALL_DIR/config/clients" "$INSTALL_DIR/backups"
  chmod 755 "$INSTALL_DIR/runtime" "$INSTALL_DIR/runtime/chromadb"
  chmod 750 "$INSTALL_DIR/config" "$INSTALL_DIR/config/auth"
  chmod 700 "$INSTALL_DIR/config/clients" "$INSTALL_DIR/backups"
  llama_key="$(openssl rand -hex 32)"
  embedding_key="$(openssl rand -hex 32)"
  postgres_password="$(openssl rand -hex 32)"
  app_image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["app_image"])' "$INSTALL_DIR/release-manifest.json")"
  if [[ "$ACCELERATOR" == "gpu" ]]; then
    llama_gpu_layers=16
    llama_gpu_layers_draft=0
    embedding_gpu_layers=99
  else
    llama_gpu_layers=0
    llama_gpu_layers_draft=0
    embedding_gpu_layers=0
  fi
  installation_started=true
  python3 - "$INSTALL_DIR/config/offline.env.template" "$INSTALL_DIR/.env" \
    "$INSTALL_DIR" "$BIND_ADDRESS" "$SERVER_ADDRESS" "$HTTP_PORT" "$(id -g)" \
    "$app_image" "$llama_key" "$embedding_key" "$postgres_password" \
    "$ACCELERATOR" "$LLAMA_CPU_IMAGE" "$LLAMA_GPU_IMAGE" "$llama_gpu_layers" \
    "$llama_gpu_layers_draft" "$embedding_gpu_layers" <<'PY'
import sys
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8")
origin = f"http://{sys.argv[5]}"
if sys.argv[6] != "80":
    origin = f"{origin}:{sys.argv[6]}"
replacements = {
    "__INSTALL_DIR__": sys.argv[3],
    "BIND_ADDRESS=0.0.0.0": f"BIND_ADDRESS={sys.argv[4]}",
    "CORS_ORIGINS=http://__SERVER_ADDRESS__": f"CORS_ORIGINS={origin}",
    "__SERVER_ADDRESS__": sys.argv[5],
    "HTTP_PORT=80": f"HTTP_PORT={sys.argv[6]}",
    "__HOST_GID__": sys.argv[7],
    "APP_IMAGE=__APP_IMAGE__": f"APP_IMAGE={sys.argv[8]}",
    "LLAMA_API_KEY=__GENERATE__": f"LLAMA_API_KEY={sys.argv[9]}",
    "EMBEDDING_API_KEY=__GENERATE__": f"EMBEDDING_API_KEY={sys.argv[10]}",
    "POSTGRES_PASSWORD=__GENERATE__": f"POSTGRES_PASSWORD={sys.argv[11]}",
    "__ACCELERATOR__": sys.argv[12],
    "__LLAMA_CPU_IMAGE__": sys.argv[13],
    "__LLAMA_GPU_IMAGE__": sys.argv[14],
    "__LLAMA_GPU_LAYERS__": sys.argv[15],
    "__LLAMA_GPU_LAYERS_DRAFT__": sys.argv[16],
    "__EMBEDDING_GPU_LAYERS__": sys.argv[17],
}
for old, new in replacements.items():
    template = template.replace(old, new)
Path(sys.argv[2]).write_text(template, encoding="utf-8")
PY
  chmod 600 "$INSTALL_DIR/.env"
  log "Generated private .env without printing secrets"
}

generate_client_credentials() {
  local client_number client_id first_client_file
  printf '{"version": 1, "clients": []}\n' > "$INSTALL_DIR/config/auth/api_keys.json"
  chmod 640 "$INSTALL_DIR/config/auth/api_keys.json"
  for ((client_number = 1; client_number <= CLIENT_COUNT; client_number++)); do
    printf -v client_id 'client-%02d' "$client_number"
    "$INSTALL_DIR/scripts/offline/manage_client.sh" add "$client_id"
  done
  first_client_file="$INSTALL_DIR/config/clients/client-01.txt"
  client_token="$(python3 - "$first_client_file" <<'PY'
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.startswith("API key: "):
        print(line.removeprefix("API key: "))
        break
else:
    raise SystemExit("first client credential does not contain an API key")
PY
)"
  log "Generated $CLIENT_COUNT unique client credential file(s)"
}

start_backend_services() {
  export OFFLINE_ENV="$INSTALL_DIR/.env"
  # shellcheck source=../offline/common.sh
  source "$INSTALL_DIR/scripts/offline/common.sh"
  compose config --quiet
  if ! compose up -d --no-build --pull never \
    postgres chromadb llama-server embedding-server; then
    print_startup_diagnostics
    exit 1
  fi
  if ! wait_for_backend_services; then
    print_startup_diagnostics
    exit 1
  fi
}

index_approved_knowledge() {
  log "First installation may spend several minutes describing each configured figure"
  run_indexer 3
}

configure_persistent_firewall() {
  "$INSTALL_DIR/scripts/offline/configure_host.sh" \
    "$LAN_CIDR" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" "$NETWORK_INTERFACE"
}

start_chatbot_and_proxy() {
  if ! compose up -d --no-build --pull never chatbot proxy; then
    print_startup_diagnostics
    exit 1
  fi
  if ! wait_for_service chatbot 60; then
    print_startup_diagnostics
    exit 1
  fi
  if ! wait_for_service proxy 30; then
    print_startup_diagnostics
    exit 1
  fi
}

verify_service_readiness() {
  local service container_id restart_policy
  curl --fail --silent --show-error \
    -H "Authorization: Bearer $client_token" \
    "$CHATBOT_ORIGIN/api/v1/ready"
  echo
  for service in postgres chromadb llama-server embedding-server chatbot proxy; do
    container_id="$(compose ps -q "$service")"
    restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$container_id")"
    [[ "$restart_policy" == "unless-stopped" ]] || {
      echo "Unexpected restart policy for $service: $restart_policy" >&2
      exit 1
    }
    log "Reboot recovery enabled for $service"
  done
  systemctl is-enabled --quiet docker.service
}

finalize_installation() {
  local client_number client_id
  : > "$INSTALL_MARKER"
  chmod 600 "$INSTALL_MARKER"
  installation_complete=true
  log "Installation complete: $INSTALL_DIR"
  log "LAN API URL: $CHATBOT_ORIGIN"
  log "Installation log: $INSTALL_LOG"
  log "Docker and chatbot services will return automatically after a normal reboot"
  echo
  echo "==================================================================="
  echo " Chatbot is ready on the LAN"
  echo "==================================================================="
  echo "Server address for other computers: $CHATBOT_ORIGIN"
  echo "Client credential files (one file per client computer):"
  for ((client_number = 1; client_number <= CLIENT_COUNT; client_number++)); do
    printf -v client_id 'client-%02d' "$client_number"
    echo "  $INSTALL_DIR/config/clients/$client_id.txt"
  done
  echo "Test from another computer:"
  echo "  curl -H \"Authorization: Bearer <API key>\" $CHATBOT_ORIGIN/api/v1/ready"
  echo "  (replace <API key> with the API key from the client's credential file)"
  echo "==================================================================="
  echo "Keep .env and api_keys.json private."
  echo "Warning: HTTP traffic and API keys are not encrypted; use only on a trusted LAN."
}