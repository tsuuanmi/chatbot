#!/usr/bin/env bash

offline_as_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
        return
    fi

    sudo "$@"
}


offline_host_network() {
    offline_require_command ip
    offline_require_command python3

    local requested="${CHATBOT_HOST_IP:-}"
    local row=""
    local interface=""
    local address=""
    local prefix=""

    if [[ -n "$requested" ]]; then
        row="$(
            ip -o -4 addr show scope global |
            awk -v target="$requested" '
                {
                    iface=$2
                    sub(/@.*/, "", iface)

                    split($4, value, "/")

                    if (value[1] == target) {
                        print iface "|" value[1] "|" value[2]
                        exit
                    }
                }
            '
        )"

        [[ -n "$row" ]] ||
            offline_die \
                "CHATBOT_HOST_IP is not assigned to a global IPv4 interface: $requested"
    else
        local route=""

        route="$(
            ip -4 route get 1.1.1.1 \
                2>/dev/null \
                || true
        )"

        if [[ -n "$route" ]]; then
            interface="$(
                awk '
                    {
                        for (i = 1; i <= NF; i++) {
                            if ($i == "dev" && i < NF) {
                                print $(i + 1)
                                exit
                            }
                        }
                    }
                ' <<<"$route"
            )"

            address="$(
                awk '
                    {
                        for (i = 1; i <= NF; i++) {
                            if ($i == "src" && i < NF) {
                                print $(i + 1)
                                exit
                            }
                        }
                    }
                ' <<<"$route"
            )"
        fi

        if [[ -n "$interface" && -n "$address" ]]; then
            row="$(
                ip -o -4 addr show \
                    dev "$interface" \
                    scope global |
                awk -v target="$address" '
                    {
                        iface=$2
                        sub(/@.*/, "", iface)

                        split($4, value, "/")

                        if (value[1] == target) {
                            print iface "|" value[1] "|" value[2]
                            exit
                        }
                    }
                '
            )"
        fi

        if [[ -z "$row" ]]; then
            row="$(
                ip -o -4 addr show scope global |
                awk '
                    {
                        iface=$2
                        sub(/@.*/, "", iface)

                        if (
                            iface ~ /^lo$/ ||
                            iface ~ /^docker/ ||
                            iface ~ /^br-/ ||
                            iface ~ /^veth/ ||
                            iface ~ /^virbr/ ||
                            iface ~ /^tailscale/
                        ) {
                            next
                        }

                        split($4, value, "/")

                        print iface "|" value[1] "|" value[2]
                        exit
                    }
                '
            )"
        fi

        [[ -n "$row" ]] ||
            offline_die \
                "Unable to detect a LAN IPv4 interface"
    fi

    IFS='|' read -r \
        interface \
        address \
        prefix \
        <<<"$row"

    [[ -n "$interface" ]] ||
        offline_die \
            "Detected network interface is empty"

    [[ -n "$address" ]] ||
        offline_die \
            "Detected host IPv4 address is empty"

    [[ -n "$prefix" ]] ||
        offline_die \
            "Detected IPv4 prefix is empty"

    case "$interface" in
        lo|docker*|br-*|veth*|virbr*|tailscale*)
            offline_die \
                "Refusing virtual/non-LAN interface: $interface"
            ;;
    esac

    local network

    network="$(
        python3 - \
            "$address" \
            "$prefix" <<'PY'
import ipaddress
import sys

address = sys.argv[1]
prefix = sys.argv[2]

interface = ipaddress.ip_interface(
    f"{address}/{prefix}"
)

if interface.version != 4:
    raise SystemExit(
        "IPv4 network required"
    )

if interface.ip.is_loopback:
    raise SystemExit(
        "Loopback address is not a LAN address"
    )

print(
    interface.network.with_prefixlen
)
PY
    )"

    printf '%s|%s|%s\n' \
        "$address" \
        "$network" \
        "$interface"
}


offline_configure_host() {
    local host_ip="$1"
    local lan_cidr="$2"
    local interface="$3"
    local gateway_bind="$4"
    local gateway_port="$5"

    offline_require_command systemctl

    [[ "$gateway_port" =~ ^[0-9]+$ ]] ||
        offline_die \
            "Invalid gateway port: $gateway_port"

    (( gateway_port >= 1 && gateway_port <= 65535 )) ||
        offline_die \
            "Gateway port is outside valid range: $gateway_port"

    echo \
        "[host] Requesting administrator access for boot/firewall configuration"

    if [[ "${EUID}" -ne 0 ]]; then
        offline_require_command sudo
        sudo -v
    fi

    offline_as_root systemctl enable \
        docker.service \
        >/dev/null

    systemctl is-enabled \
        --quiet \
        docker.service ||
        offline_die \
            "Docker service is not enabled at boot"

    echo \
        "[host] Docker boot startup enabled"

    if [[ "$gateway_bind" == "127.0.0.1" ]]; then
        echo \
            "[host] Gateway is loopback-only; LAN firewall is not required"
        return 0
    fi

    if [[ \
        "$gateway_bind" != "0.0.0.0" &&
        "$gateway_bind" != "$host_ip" \
    ]]; then
        offline_die \
            "GATEWAY_BIND must be 0.0.0.0, 127.0.0.1, or detected host IP $host_ip"
    fi

    local iptables_bin

    iptables_bin="$(
        command -v iptables \
            || true
    )"

    [[ -n "$iptables_bin" ]] ||
        offline_die \
            "iptables is required for LAN-only Docker port isolation"

    offline_as_root "$iptables_bin" \
        -S DOCKER-USER \
        >/dev/null ||
        offline_die \
            "Docker DOCKER-USER firewall chain is unavailable"

    offline_as_root "$iptables_bin" \
        -m conntrack \
        -h \
        >/dev/null 2>&1 ||
        offline_die \
            "iptables conntrack matching is unavailable"

    python3 - \
        "$host_ip" \
        "$lan_cidr" <<'PY'
import ipaddress
import sys

address = ipaddress.ip_address(
    sys.argv[1]
)

network = ipaddress.ip_network(
    sys.argv[2],
    strict=False,
)

if address.version != 4:
    raise SystemExit(
        "host address must be IPv4"
    )

if network.version != 4:
    raise SystemExit(
        "LAN network must be IPv4"
    )

if address not in network:
    raise SystemExit(
        f"host address {address} is outside LAN {network}"
    )

if network.prefixlen < 8:
    raise SystemExit(
        f"refusing excessively broad LAN network: {network}"
    )
PY

    local config_tmp
    local program_tmp
    local unit_tmp

    config_tmp="$(mktemp)"
    program_tmp="$(mktemp)"
    unit_tmp="$(mktemp)"

    cleanup_host_files() {
        rm -f \
            "$config_tmp" \
            "$program_tmp" \
            "$unit_tmp"
    }

    trap \
        cleanup_host_files \
        RETURN

    cat >"$config_tmp" <<EOF
CHATBOT_HOST_IP=$host_ip
CHATBOT_LAN_CIDR=$lan_cidr
CHATBOT_NETWORK_INTERFACE=$interface
CHATBOT_GATEWAY_PORT=$gateway_port
CHATBOT_PROXY_PORT=8080
EOF

    cat >"$program_tmp" <<EOF
#!/bin/sh
set -eu

IPTABLES='$iptables_bin'
CHAIN='CHATBOT'
CONFIG='/etc/chatbot/firewall.conf'

. "\$CONFIG"

"\$IPTABLES" -w 5 -N "\$CHAIN" 2>/dev/null || true
"\$IPTABLES" -w 5 -F "\$CHAIN"

"\$IPTABLES" -w 5 -A "\$CHAIN" \
    -s "\$CHATBOT_LAN_CIDR" \
    -p tcp \
    --dport "\$CHATBOT_PROXY_PORT" \
    -m conntrack \
    --ctdir ORIGINAL \
    --ctorigdstport "\$CHATBOT_GATEWAY_PORT" \
    -j ACCEPT

"\$IPTABLES" -w 5 -A "\$CHAIN" \
    -p tcp \
    --dport "\$CHATBOT_PROXY_PORT" \
    -m conntrack \
    --ctdir ORIGINAL \
    --ctorigdstport "\$CHATBOT_GATEWAY_PORT" \
    -j DROP

"\$IPTABLES" -w 5 -A "\$CHAIN" \
    -j RETURN

if ! "\$IPTABLES" -w 5 \
    -C DOCKER-USER \
    -j "\$CHAIN" \
    2>/dev/null
then
    "\$IPTABLES" -w 5 \
        -I DOCKER-USER 1 \
        -j "\$CHAIN"
fi
EOF

    cat >"$unit_tmp" <<'EOF'
[Unit]
Description=Chatbot LAN Docker firewall
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

    offline_as_root install \
        -d \
        -o root \
        -g root \
        -m 0755 \
        /etc/chatbot

    offline_as_root install \
        -o root \
        -g root \
        -m 0644 \
        "$config_tmp" \
        /etc/chatbot/firewall.conf

    offline_as_root install \
        -o root \
        -g root \
        -m 0755 \
        "$program_tmp" \
        /usr/local/sbin/chatbot-firewall

    offline_as_root install \
        -o root \
        -g root \
        -m 0644 \
        "$unit_tmp" \
        /etc/systemd/system/chatbot-firewall.service

    offline_as_root systemctl \
        daemon-reload

    offline_as_root systemctl enable \
        chatbot-firewall.service \
        >/dev/null

    offline_as_root systemctl restart \
        chatbot-firewall.service

    systemctl is-enabled \
        --quiet \
        chatbot-firewall.service ||
        offline_die \
            "Chatbot firewall service is not enabled"

    systemctl is-active \
        --quiet \
        chatbot-firewall.service ||
        offline_die \
            "Chatbot firewall service is not active"

    offline_as_root "$iptables_bin" \
        -C DOCKER-USER \
        -j CHATBOT \
        >/dev/null ||
        offline_die \
            "Chatbot firewall is not connected to DOCKER-USER"

    echo \
        "[host] LAN firewall active: $lan_cidr -> tcp/$gateway_port"
}


offline_host_accept() {
    offline_require_command systemctl

    systemctl is-enabled \
        --quiet \
        docker.service ||
        offline_die \
            "Docker service is not enabled at boot"

    echo \
        "PASS docker boot startup enabled"

    local service
    local container_id
    local restart_policy

    for service in \
        postgres \
        llama-server \
        chatbot \
        proxy
    do
        container_id="$(
            offline_runtime_compose \
                ps -q "$service"
        )"

        [[ -n "$container_id" ]] ||
            offline_die \
                "Cannot inspect restart policy for $service"

        restart_policy="$(
            docker inspect \
                --format \
                '{{.HostConfig.RestartPolicy.Name}}' \
                "$container_id"
        )"

        [[ "$restart_policy" == "unless-stopped" ]] ||
            offline_die \
                "Unexpected restart policy for $service: $restart_policy"

        echo \
            "PASS reboot restart policy $service=$restart_policy"
    done

    local gateway_bind

    gateway_bind="$(
        offline_env_value GATEWAY_BIND
    )"

    gateway_bind="${gateway_bind:-0.0.0.0}"

    if [[ "$gateway_bind" == "127.0.0.1" ]]; then
        echo \
            "PASS loopback-only gateway; LAN firewall not required"
        return 0
    fi

    [[ -f /etc/chatbot/firewall.conf ]] ||
        offline_die \
            "Chatbot firewall configuration is missing"

    [[ -f /etc/systemd/system/chatbot-firewall.service ]] ||
        offline_die \
            "Chatbot firewall systemd unit is missing"

    systemctl is-enabled \
        --quiet \
        chatbot-firewall.service ||
        offline_die \
            "Chatbot firewall service is not enabled"

    systemctl is-active \
        --quiet \
        chatbot-firewall.service ||
        offline_die \
            "Chatbot firewall service is not active"

    local expected_cidr
    local expected_port
    local actual_cidr
    local actual_port

    expected_cidr="$(
        offline_env_value CHATBOT_LAN_CIDR
    )"

    expected_port="$(
        offline_env_value GATEWAY_PORT
    )"

    expected_port="${expected_port:-18080}"

    actual_cidr="$(
        awk -F= '$1 == "CHATBOT_LAN_CIDR" { print substr($0, index($0, "=") + 1) }' \
            /etc/chatbot/firewall.conf
    )"

    actual_port="$(
        awk -F= '$1 == "CHATBOT_GATEWAY_PORT" { print substr($0, index($0, "=") + 1) }' \
            /etc/chatbot/firewall.conf
    )"

    [[ -n "$expected_cidr" ]] ||
        offline_die \
            "CHATBOT_LAN_CIDR is missing from installation"

    [[ "$actual_cidr" == "$expected_cidr" ]] ||
        offline_die \
            "Installed firewall LAN differs from runtime configuration"

    [[ "$actual_port" == "$expected_port" ]] ||
        offline_die \
            "Installed firewall port differs from runtime configuration"

    echo \
        "PASS persistent LAN firewall=$expected_cidr tcp/$expected_port"
}
