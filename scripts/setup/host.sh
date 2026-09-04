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
  if [[ "$reset_incomplete_installation" == true && "$ACCELERATOR" == "gpu" ]]; then
    stop_incomplete_gpu_containers
  fi
  if [[ "$ACCELERATOR" == "gpu" ]]; then
    validate_residual_gpu_memory
  fi
}

validate_residual_gpu_memory() {
  if ! gpu_memory_output="$(
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>&1
  )"; then
    echo "Could not measure total NVIDIA GPU memory use:" >&2
    echo "$gpu_memory_output" >&2
    exit 1
  fi
  if ! remaining_compute_processes="$(
    nvidia-smi --query-compute-apps=pid,process_name,used_memory \
      --format=csv,noheader,nounits 2>&1
  )"; then
    echo "Could not list residual NVIDIA GPU processes:" >&2
    echo "$remaining_compute_processes" >&2
    exit 1
  fi
  if ! remaining_gpu_mb="$(
    awk '
      {
        value = $0
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        if (value !~ /^[0-9]+([.][0-9]+)?$/) {
          invalid = 1
          next
        }
        total += value
        count += 1
      }
      END {
        if (invalid || count == 0) exit 1
        printf "%.0f", total
      }
    ' <<< "$gpu_memory_output"
  )"; then
    echo "NVIDIA returned an invalid total GPU memory measurement:" >&2
    echo "$gpu_memory_output" >&2
    exit 1
  fi
  if [[ -n "$remaining_compute_processes" ]]; then
    echo "GPU processes are using memory before installation:" >&2
    echo "$remaining_compute_processes" >&2
  fi
  echo "Total residual GPU memory: ${remaining_gpu_mb} MiB" >&2
  if (( remaining_gpu_mb >= residual_gpu_limit_mb )); then
    echo "Residual GPU usage is at least ${residual_gpu_limit_mb} MiB." >&2
    echo "Stop substantial GPU processes safely, then run setup.sh again." >&2
    exit 1
  fi
  if (( remaining_gpu_mb > 0 )); then
    log "Continuing because total residual GPU usage is below ${residual_gpu_limit_mb} MiB"
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