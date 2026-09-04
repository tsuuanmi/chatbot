# Host-machine steps: LAN detection, firewall preflight, and bind address validation.

select_lan_network() {
  local network_selection
  network_selection="$(
    python3 "$INSTALL_DIR/scripts/offline/detect_network.py" \
      --server-address "$SERVER_ADDRESS" --lan-cidr "$LAN_CIDR"
  )"
  read -r SERVER_ADDRESS LAN_CIDR NETWORK_INTERFACE <<< "$network_selection"
  [[ -n "$SERVER_ADDRESS" && -n "$LAN_CIDR" && -n "$NETWORK_INTERFACE" ]] || {
    echo "Network detection returned incomplete information." >&2
    exit 1
  }
  log "Selected interface: $NETWORK_INTERFACE"
  log "Selected server address: $SERVER_ADDRESS"
  log "Selected trusted LAN: $LAN_CIDR"
}

preflight_host_firewall() {
  "$INSTALL_DIR/scripts/offline/configure_host.sh" --preflight \
    "$LAN_CIDR" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" "$NETWORK_INTERFACE"
  if [[ "$ACCELERATOR" == "gpu" ]]; then
    validate_residual_gpu_memory
  fi
}

validate_residual_gpu_memory() {
  local gpu_memory_output remaining_compute_processes
  local gpu_index gpu_total_mb gpu_used_mb extra allowed_residual_mb
  local total_residual_mb=0 blocked=false
  local -a gpu_memory_lines=()
  if ! gpu_memory_output="$(
    nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits 2>&1
  )"; then
    echo "Could not measure NVIDIA GPU memory capacity and use:" >&2
    echo "$gpu_memory_output" >&2
    exit 1
  fi
  mapfile -t gpu_memory_lines <<< "$gpu_memory_output"
  (( ${#gpu_memory_lines[@]} > 0 )) || {
    echo "NVIDIA returned no GPU memory measurements." >&2
    exit 1
  }
  for gpu_index in "${!gpu_memory_lines[@]}"; do
    IFS=, read -r gpu_total_mb gpu_used_mb extra <<< "${gpu_memory_lines[$gpu_index]}"
    gpu_total_mb="${gpu_total_mb//[[:space:]]/}"
    gpu_used_mb="${gpu_used_mb//[[:space:]]/}"
    [[ -z "$extra" && "$gpu_total_mb" =~ ^[0-9]+$ && "$gpu_used_mb" =~ ^[0-9]+$ ]] || {
      echo "NVIDIA returned an invalid GPU memory measurement:" >&2
      echo "${gpu_memory_lines[$gpu_index]}" >&2
      exit 1
    }
    allowed_residual_mb=$((gpu_total_mb - minimum_gpu_memory_mib))
    if (( allowed_residual_mb < residual_gpu_limit_mb )); then
      allowed_residual_mb=$residual_gpu_limit_mb
    fi
    total_residual_mb=$((total_residual_mb + gpu_used_mb))
    echo "GPU $gpu_index residual memory: ${gpu_used_mb} MiB of ${gpu_total_mb} MiB (limit ${allowed_residual_mb} MiB)" >&2
    if (( gpu_used_mb >= allowed_residual_mb )); then
      echo "GPU $gpu_index does not have enough free memory for the selected profile." >&2
      blocked=true
    fi
  done
  if ! remaining_compute_processes="$(
    nvidia-smi --query-compute-apps=pid,process_name,used_memory \
      --format=csv,noheader,nounits 2>&1
  )"; then
    echo "Could not list residual NVIDIA GPU processes:" >&2
    echo "$remaining_compute_processes" >&2
    exit 1
  fi
  if [[ -n "$remaining_compute_processes" ]]; then
    echo "GPU processes are using memory before installation:" >&2
    echo "$remaining_compute_processes" >&2
  fi
  echo "Total residual GPU memory: ${total_residual_mb} MiB" >&2
  if [[ "$blocked" == true ]]; then
    echo "Stop substantial GPU processes safely, then run setup.sh again." >&2
    exit 1
  fi
  if (( total_residual_mb > 0 )); then
    log "Continuing because every GPU remains within its capacity-aware residual limit"
  else
    log "GPU reports no residual memory use"
  fi
}

validate_bind_address() {
  sudo python3 - "$BIND_ADDRESS" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" <<'PY'
import ipaddress
import socket
import sys

bind_address, server_address, raw_http_port, raw_ssh_port = sys.argv[1:]
for label, raw_address in (
    ("bind address", bind_address),
    ("server address", server_address),
):
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError:
        raise SystemExit(f"invalid IPv4 {label}: {raw_address}") from None
    if address.version != 4:
        raise SystemExit(f"only IPv4 {label}es are supported: {raw_address}")

for label, raw_port in (("HTTP", raw_http_port), ("SSH", raw_ssh_port)):
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit(f"invalid {label} port: {raw_port}") from None

http_port = int(raw_http_port)
with socket.socket() as listener:
    try:
        listener.bind((bind_address, http_port))
    except OSError as error:
        raise SystemExit(
            f"bind address is unavailable or port is in use: "
            f"{bind_address}:{http_port}: {error}"
        ) from error
PY
  if [[ "$HTTP_PORT" == "80" ]]; then
    CHATBOT_ORIGIN="http://$SERVER_ADDRESS"
  else
    CHATBOT_ORIGIN="http://$SERVER_ADDRESS:$HTTP_PORT"
  fi
  log "LAN API URL will be: $CHATBOT_ORIGIN"
}