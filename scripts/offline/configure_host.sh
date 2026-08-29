#!/usr/bin/env bash
set -Eeuo pipefail

if (( $# != 4 )); then
  echo "usage: $0 LAN_CIDR SERVER_ADDRESS HTTP_PORT SSH_PORT" >&2
  exit 2
fi

LAN_CIDR="$1"
SERVER_ADDRESS="$2"
HTTP_PORT="$3"
SSH_PORT="$4"
FIREWALL_PROGRAM="/usr/local/sbin/chatbot-bca-firewall"
FIREWALL_UNIT="/etc/systemd/system/chatbot-bca-firewall.service"
FIREWALL_STATE="/etc/chatbot-bca/firewall.conf"

log() {
  printf '[host %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

for command in awk install iptables mktemp python3 sudo systemctl ufw; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required host-setup command not found: $command" >&2
    exit 1
  }
done

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

log "Requesting administrator access for firewall and boot configuration"
sudo -v
iptables_path="$(command -v iptables)"
log "Preflighting the Docker DOCKER-USER chain and conntrack matcher"
sudo "$iptables_path" -S DOCKER-USER >/dev/null
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

previous_state="$(sudo cat "$FIREWALL_STATE" 2>/dev/null || true)"
if [[ -n "$previous_state" ]]; then
  previous_lan="$(awk -F= '$1 == "LAN_CIDR" {print $2}' <<< "$previous_state")"
  previous_http_port="$(awk -F= '$1 == "HTTP_PORT" {print $2}' <<< "$previous_state")"
  previous_ssh_port="$(awk -F= '$1 == "SSH_PORT" {print $2}' <<< "$previous_state")"
  if [[ -n "$previous_lan" && -n "$previous_http_port" ]]; then
    log "Removing the previous installer-owned UFW HTTP rule"
    sudo ufw --force delete allow from "$previous_lan" to any \
      port "$previous_http_port" proto tcp >/dev/null 2>&1 || true
  fi
  if [[ -n "$previous_lan" && -n "$previous_ssh_port" ]]; then
    log "Removing the previous installer-owned UFW SSH rule"
    sudo ufw --force delete allow from "$previous_lan" to any \
      port "$previous_ssh_port" proto tcp >/dev/null 2>&1 || true
  fi
fi

log "Allowing SSH port $SSH_PORT from $LAN_CIDR before enabling UFW"
sudo ufw allow from "$LAN_CIDR" to any port "$SSH_PORT" proto tcp \
  comment 'Chatbot LAN SSH'
log "Allowing chatbot HTTP port $HTTP_PORT from $LAN_CIDR"
sudo ufw allow from "$LAN_CIDR" to any port "$HTTP_PORT" proto tcp \
  comment 'Chatbot LAN HTTP'
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw --force enable

firewall_program_tmp="$(mktemp)"
firewall_unit_tmp="$(mktemp)"
firewall_state_tmp="$(mktemp)"
cleanup() {
  rm -f "$firewall_program_tmp" "$firewall_unit_tmp" "$firewall_state_tmp"
}
trap cleanup EXIT

cat > "$firewall_program_tmp" <<EOF
#!/bin/sh
set -eu
IPTABLES='$iptables_path'
CHAIN='CHATBOT_BCA'
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

cat > "$firewall_state_tmp" <<EOF
LAN_CIDR=$LAN_CIDR
SERVER_ADDRESS=$SERVER_ADDRESS
HTTP_PORT=$HTTP_PORT
SSH_PORT=$SSH_PORT
EOF

cat > "$firewall_unit_tmp" <<'EOF'
[Unit]
Description=Chatbot Docker LAN firewall
Requires=docker.service
After=docker.service
PartOf=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/chatbot-bca-firewall
ExecReload=/usr/local/sbin/chatbot-bca-firewall
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

log "Installing persistent DOCKER-USER firewall service"
sudo install -o root -g root -m 0755 "$firewall_program_tmp" "$FIREWALL_PROGRAM"
sudo install -o root -g root -m 0644 "$firewall_unit_tmp" "$FIREWALL_UNIT"
sudo install -o root -g root -m 0755 -d /etc/chatbot-bca
sudo install -o root -g root -m 0600 "$firewall_state_tmp" "$FIREWALL_STATE"
sudo systemctl enable docker.service
sudo systemctl daemon-reload
sudo systemctl enable chatbot-bca-firewall.service
sudo systemctl restart chatbot-bca-firewall.service
sudo systemctl is-enabled --quiet chatbot-bca-firewall.service
sudo systemctl is-active --quiet chatbot-bca-firewall.service

log "Host firewall is active for $SERVER_ADDRESS"
sudo ufw status verbose
sudo "$iptables_path" -L CHATBOT_BCA -n --line-numbers
