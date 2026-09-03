#!/usr/bin/env bash
set -Eeuo pipefail

PREFLIGHT=false
if [[ "${1:-}" == "--preflight" ]]; then
  PREFLIGHT=true
  shift
fi
if (( $# != 5 )); then
  echo "usage: $0 [--preflight] LAN_CIDR SERVER_ADDRESS HTTP_PORT SSH_PORT NETWORK_INTERFACE" >&2
  exit 2
fi

LAN_CIDR="$1"
SERVER_ADDRESS="$2"
HTTP_PORT="$3"
SSH_PORT="$4"
NETWORK_INTERFACE="$5"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=host_platform.sh
source "$SCRIPT_DIR/host_platform.sh"
HOST_PLATFORM="$(host_platform)"
FIREWALL_BACKEND="$(host_firewall_backend "$HOST_PLATFORM")"
FIREWALL_PROGRAM="/usr/local/sbin/chatbot-firewall"
FIREWALL_UNIT="/etc/systemd/system/chatbot-firewall.service"
FIREWALL_STATE="/etc/chatbot/firewall.conf"
FIREWALL_ZONE=""
iptables_path="/usr/sbin/iptables"

log() {
  printf '[host %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

if [[ "$FIREWALL_BACKEND" == "firewalld" ]]; then
  firewall_command=firewall-cmd
else
  firewall_command="$FIREWALL_BACKEND"
fi
for command in awk install mktemp python3 sudo systemctl "$firewall_command"; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required host-setup command not found: $command" >&2
    exit 1
  }
done
[[ -x "$iptables_path" ]] || {
  echo "Required system command not found: $iptables_path" >&2
  exit 1
}

python3 - "$LAN_CIDR" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" <<'PY'
import ipaddress
import sys

raw_network, raw_address, raw_http_port, raw_ssh_port = sys.argv[1:]
try:
    network = ipaddress.ip_network(raw_network, strict=False)
except ValueError:
    raise SystemExit(f"invalid IPv4 LAN CIDR: {raw_network}") from None
try:
    address = ipaddress.ip_address(raw_address)
except ValueError:
    raise SystemExit(f"invalid IPv4 server address: {raw_address}") from None
if network.version != 4 or address.version != 4:
    raise SystemExit("host firewall supports IPv4 only")
if address not in network:
    raise SystemExit(f"server address {address} is outside LAN CIDR {network}")
if network.prefixlen < 8:
    raise SystemExit(f"LAN CIDR is too broad for automatic trust: {network}")
for label, raw_port in (("HTTP", raw_http_port), ("SSH", raw_ssh_port)):
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit(f"invalid {label} port: {raw_port}") from None
PY

firewalld_zone() {
  local zone
  zone="$(sudo firewall-cmd --get-zone-of-interface="$NETWORK_INTERFACE" 2>/dev/null || true)"
  if [[ -z "$zone" || "$zone" == "no zone" ]]; then
    zone="$(sudo firewall-cmd --get-default-zone)"
  fi
  [[ "$zone" =~ ^[[:alnum:]_-]+$ ]] || {
    echo "Could not determine the firewalld zone for $NETWORK_INTERFACE." >&2
    return 1
  }
  [[ "$(sudo firewall-cmd --zone="$zone" --get-target)" != "ACCEPT" ]] || {
    echo "Refusing firewalld zone with an ACCEPT target: $zone" >&2
    return 1
  }
  printf '%s\n' "$zone"
}

firewalld_rule() {
  local cidr="$1" port="$2"
  printf 'rule family="ipv4" source address="%s" port port="%s" protocol="tcp" accept' \
    "$cidr" "$port"
}

assert_firewalld_port_restricted() {
  local port rules
  port="$1"
  rules="$(sudo firewall-cmd --zone="$FIREWALL_ZONE" --list-rich-rules)"
  FIREWALL_RULES="$rules" python3 - "$port" <<'PY'
import ipaddress
import os
import re
import sys

port = sys.argv[1]
for rule in os.environ["FIREWALL_RULES"].splitlines():
    if f'port port="{port}" protocol="tcp"' not in rule or "accept" not in rule:
        continue
    source = re.search(r'source address="([^"]+)"', rule)
    if source is None:
        raise SystemExit(f"firewalld has a broad accepting rule for TCP port {port}")
    try:
        network = ipaddress.ip_network(source.group(1), strict=False)
    except ValueError:
        raise SystemExit(f"firewalld has an invalid source rule for TCP port {port}") from None
    if network.prefixlen == 0:
        raise SystemExit(f"firewalld has a broad accepting rule for TCP port {port}")
PY
}

verify_docker_user_chain() {
  local first_forward_rule
  sudo "$iptables_path" -S DOCKER-USER >/dev/null || {
    echo "Docker does not provide the required DOCKER-USER firewall chain." >&2
    return 1
  }
  first_forward_rule="$(
    sudo "$iptables_path" -S FORWARD | awk '$1 == "-A" && $2 == "FORWARD" { print; exit }' || true
  )"
  [[ "$first_forward_rule" == "-A FORWARD -j DOCKER-USER" ]] || {
    echo "Docker does not route forwarded traffic through DOCKER-USER before other FORWARD rules." >&2
    return 1
  }
}

write_firewall_state() {
  local state_tmp
  state_tmp="$(mktemp)"
  cat > "$state_tmp" <<EOF
FIREWALL_BACKEND=$FIREWALL_BACKEND
FIREWALL_ZONE=$FIREWALL_ZONE
LAN_CIDR=$LAN_CIDR
SERVER_ADDRESS=$SERVER_ADDRESS
HTTP_PORT=$HTTP_PORT
SSH_PORT=$SSH_PORT
EOF
  sudo install -o root -g root -m 0755 -d /etc/chatbot
  sudo install -o root -g root -m 0600 "$state_tmp" "$FIREWALL_STATE"
  rm -f "$state_tmp"
}

remove_previous_rules() {
  local previous_state previous_backend previous_lan previous_http_port previous_ssh_port previous_zone
  previous_state="$(sudo cat "$FIREWALL_STATE" 2>/dev/null || true)"
  [[ -n "$previous_state" ]] || return 0
  previous_backend="$(awk -F= '$1 == "FIREWALL_BACKEND" {print $2}' <<< "$previous_state")"
  previous_backend="${previous_backend:-ufw}"
  previous_lan="$(awk -F= '$1 == "LAN_CIDR" {print $2}' <<< "$previous_state")"
  previous_http_port="$(awk -F= '$1 == "HTTP_PORT" {print $2}' <<< "$previous_state")"
  previous_ssh_port="$(awk -F= '$1 == "SSH_PORT" {print $2}' <<< "$previous_state")"
  previous_zone="$(awk -F= '$1 == "FIREWALL_ZONE" {print $2}' <<< "$previous_state")"
  [[ -n "$previous_lan" && -n "$previous_http_port" ]] || return 0
  if [[ "$previous_backend" == "firewalld" \
    && "$previous_lan" == "$LAN_CIDR" \
    && "$previous_http_port" == "$HTTP_PORT" \
    && "$previous_ssh_port" == "$SSH_PORT" \
    && "$previous_zone" == "$FIREWALL_ZONE" ]]; then
    log "Keeping unchanged installer-owned firewalld rules"
    return 0
  fi

  case "$previous_backend" in
    ufw)
      log "Removing previous installer-owned UFW rules"
      sudo ufw --force delete allow from "$previous_lan" to any \
        port "$previous_http_port" proto tcp >/dev/null 2>&1 || true
      if [[ -n "$previous_ssh_port" ]]; then
        sudo ufw --force delete allow from "$previous_lan" to any \
          port "$previous_ssh_port" proto tcp >/dev/null 2>&1 || true
      fi
      ;;
    firewalld)
      [[ -n "$previous_zone" ]] || return 0
      log "Removing previous installer-owned firewalld rules"
      sudo firewall-cmd --zone="$previous_zone" --remove-rich-rule \
        "$(firewalld_rule "$previous_lan" "$previous_http_port")" >/dev/null 2>&1 || true
      sudo firewall-cmd --permanent --zone="$previous_zone" --remove-rich-rule \
        "$(firewalld_rule "$previous_lan" "$previous_http_port")" >/dev/null 2>&1 || true
      if [[ -n "$previous_ssh_port" ]]; then
        sudo firewall-cmd --zone="$previous_zone" --remove-rich-rule \
          "$(firewalld_rule "$previous_lan" "$previous_ssh_port")" >/dev/null 2>&1 || true
        sudo firewall-cmd --permanent --zone="$previous_zone" --remove-rich-rule \
          "$(firewalld_rule "$previous_lan" "$previous_ssh_port")" >/dev/null 2>&1 || true
      fi
      ;;
    *)
      echo "Unsupported previous firewall backend: $previous_backend" >&2
      return 1
      ;;
  esac
}

preflight_host_firewall() {
  log "Requesting administrator access for firewall and boot configuration"
  sudo -v
  if ! sudo "$iptables_path" -m conntrack -h >/dev/null; then
    echo "Docker firewall conntrack matching is unavailable." >&2
    return 1
  fi
  verify_docker_user_chain
  if [[ "$FIREWALL_BACKEND" == "firewalld" ]]; then
    FIREWALL_ZONE="$(firewalld_zone)"
    sudo firewall-cmd --state >/dev/null
    assert_firewalld_port_restricted "$SSH_PORT"
    assert_firewalld_port_restricted "$HTTP_PORT"
  fi
}

configure_ufw() {
  write_firewall_state
  log "Allowing SSH port $SSH_PORT from $LAN_CIDR before enabling UFW"
  sudo ufw allow from "$LAN_CIDR" to any port "$SSH_PORT" proto tcp \
    comment 'Chatbot LAN SSH'
  log "Allowing chatbot HTTP port $HTTP_PORT from $LAN_CIDR"
  sudo ufw allow from "$LAN_CIDR" to any port "$HTTP_PORT" proto tcp \
    comment 'Chatbot LAN HTTP'
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw --force enable
}

configure_firewalld() {
  local service port rule
  FIREWALL_ZONE="$(firewalld_zone)"
  sudo firewall-cmd --state >/dev/null
  assert_firewalld_port_restricted "$SSH_PORT"
  assert_firewalld_port_restricted "$HTTP_PORT"
  for port in "$SSH_PORT" "$HTTP_PORT"; do
    rule="$(firewalld_rule "$LAN_CIDR" "$port")"
    sudo firewall-cmd --zone="$FIREWALL_ZONE" --add-rich-rule "$rule"
    sudo firewall-cmd --permanent --zone="$FIREWALL_ZONE" --add-rich-rule "$rule"
    sudo firewall-cmd --zone="$FIREWALL_ZONE" --query-rich-rule "$rule" >/dev/null
    sudo firewall-cmd --permanent --zone="$FIREWALL_ZONE" --query-rich-rule "$rule" >/dev/null
  done
  for service in ssh; do
    sudo firewall-cmd --zone="$FIREWALL_ZONE" --remove-service="$service" >/dev/null 2>&1 || true
    sudo firewall-cmd --permanent --zone="$FIREWALL_ZONE" --remove-service="$service" >/dev/null 2>&1 || true
  done
  if [[ "$HTTP_PORT" == "80" ]]; then
    sudo firewall-cmd --zone="$FIREWALL_ZONE" --remove-service=http >/dev/null 2>&1 || true
    sudo firewall-cmd --permanent --zone="$FIREWALL_ZONE" --remove-service=http >/dev/null 2>&1 || true
  fi
  for port in "$SSH_PORT" "$HTTP_PORT"; do
    sudo firewall-cmd --zone="$FIREWALL_ZONE" --remove-port="${port}/tcp" >/dev/null 2>&1 || true
    sudo firewall-cmd --permanent --zone="$FIREWALL_ZONE" --remove-port="${port}/tcp" >/dev/null 2>&1 || true
  done
  remove_previous_rules
  write_firewall_state
  log "Restricted SSH port $SSH_PORT and chatbot HTTP port $HTTP_PORT to $LAN_CIDR in firewalld zone $FIREWALL_ZONE"
}

preflight_host_firewall
if [[ "$PREFLIGHT" == true ]]; then
  exit 0
fi
log "Rechecking the Docker DOCKER-USER chain after backend startup"
verify_docker_user_chain
if sudo "$iptables_path" -C DOCKER-USER -p tcp --dport 80 -m conntrack \
  --ctdir ORIGINAL --ctorigdstport "$HTTP_PORT" -j ACCEPT 2>/dev/null; then
  :
else
  conntrack_status=$?
  if (( conntrack_status != 1 )); then
    echo "Docker firewall conntrack matching is unavailable." >&2
    exit "$conntrack_status"
  fi
fi

case "$FIREWALL_BACKEND" in
  ufw)
    remove_previous_rules
    configure_ufw
    ;;
  firewalld) configure_firewalld ;;
esac

firewall_program_tmp="$(mktemp)"
firewall_unit_tmp="$(mktemp)"
cleanup() {
  rm -f "$firewall_program_tmp" "$firewall_unit_tmp"
}
trap cleanup EXIT

cat > "$firewall_program_tmp" <<EOF
#!/bin/sh
set -eu
IPTABLES='$iptables_path'
CHAIN='CHATBOT'
LAN_CIDR='$LAN_CIDR'
HTTP_PORT='$HTTP_PORT'
PROXY_CONTAINER_PORT='80'

"\$IPTABLES" -N "\$CHAIN" 2>/dev/null || true
"\$IPTABLES" -F "\$CHAIN"
# DOCKER-USER sees the proxy's post-DNAT port 80. Conntrack also matches the
# configured original host port so unrelated Docker port-80 mappings are untouched.
"\$IPTABLES" -A "\$CHAIN" -s "\$LAN_CIDR" -p tcp \
  --dport "\$PROXY_CONTAINER_PORT" -m conntrack --ctdir ORIGINAL \
  --ctorigdstport "\$HTTP_PORT" -j ACCEPT
"\$IPTABLES" -A "\$CHAIN" -p tcp --dport "\$PROXY_CONTAINER_PORT" \
  -m conntrack --ctdir ORIGINAL --ctorigdstport "\$HTTP_PORT" -j DROP
"\$IPTABLES" -A "\$CHAIN" -j RETURN
if ! "\$IPTABLES" -C DOCKER-USER -j "\$CHAIN" 2>/dev/null; then
  "\$IPTABLES" -I DOCKER-USER 1 -j "\$CHAIN"
fi
EOF

cat > "$firewall_unit_tmp" <<'EOF'
[Unit]
Description=Chatbot Docker LAN firewall
Requires=docker.service
After=docker.service
PartOf=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/chatbot-firewall
ExecReload=/usr/local/sbin/chatbot-firewall
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

log "Installing persistent DOCKER-USER firewall service"
sudo install -o root -g root -m 0755 "$firewall_program_tmp" "$FIREWALL_PROGRAM"
sudo install -o root -g root -m 0644 "$firewall_unit_tmp" "$FIREWALL_UNIT"
sudo systemctl enable docker.service
sudo systemctl daemon-reload
sudo systemctl enable chatbot-firewall.service
sudo systemctl restart chatbot-firewall.service
sudo systemctl is-enabled --quiet chatbot-firewall.service
sudo systemctl is-active --quiet chatbot-firewall.service

log "Host firewall is active for $SERVER_ADDRESS"
case "$FIREWALL_BACKEND" in
  ufw) sudo ufw status verbose ;;
  firewalld) sudo firewall-cmd --zone="$FIREWALL_ZONE" --list-rich-rules ;;
esac
sudo "$iptables_path" -L CHATBOT -n --line-numbers
