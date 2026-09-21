#!/usr/bin/env bash

offline_die() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

offline_require_command() {
    command -v "$1" >/dev/null 2>&1 ||
        offline_die "Required command not found: $1"
}

offline_require_installation() {
    [[ -n "${OFFLINE_ROOT:-}" ]] ||
        offline_die "OFFLINE_ROOT is not configured"

    [[ -f "$OFFLINE_ROOT/.env" ]] ||
        offline_die \
            "Installation is not configured; run make install first"

    [[ -f "$OFFLINE_ROOT/versions.env" ]] ||
        offline_die "versions.env is missing"

    [[ -f "$OFFLINE_ROOT/versions.gpu.env" ]] ||
        offline_die "versions.gpu.env is missing"
}

offline_project_name() {
    printf '%s\n' \
        "${CHATBOT_PROJECT_NAME:-chatbot}"
}

offline_manifest_value() {
    local file="$1"
    local key="$2"

    awk -F= \
        -v key="$key" \
        '$1 == key {
            print substr($0, index($0, "=") + 1)
        }' \
        "$file"
}

offline_env_value() {
    local key="$1"

    awk -F= \
        -v key="$key" \
        '$1 == key {
            print substr($0, index($0, "=") + 1)
        }' \
        "$OFFLINE_ROOT/.env"
}

offline_set_env() {
    local key="$1"
    local value="$2"

    python3 - \
        "$OFFLINE_ROOT/.env" \
        "$key" \
        "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]

lines = path.read_text(
    encoding="utf-8"
).splitlines()

output = []
found = False

for line in lines:
    current = line.partition("=")[0]

    if current == key:
        output.append(
            f"{key}={value}"
        )
        found = True
    else:
        output.append(line)

if not found:
    output.append(
        f"{key}={value}"
    )

path.write_text(
    "\n".join(output) + "\n",
    encoding="utf-8",
)
PY
}

offline_compose() {
    env \
        -u LLAMA_GPU_IMAGE \
        -u LLAMA_GPU_LAYERS \
        -u LLAMA_GPU_LAYERS_DRAFT \
        docker compose \
        --project-directory "$OFFLINE_ROOT" \
        --project-name "$(offline_project_name)" \
        --env-file "$OFFLINE_ROOT/.env" \
        --env-file "$OFFLINE_ROOT/versions.env" \
        "$@"
}

offline_gpu_compose() {
    env \
        -u LLAMA_GPU_IMAGE \
        -u LLAMA_GPU_LAYERS \
        -u LLAMA_GPU_LAYERS_DRAFT \
        docker compose \
        --project-directory "$OFFLINE_ROOT" \
        --project-name "$(offline_project_name)" \
        --env-file "$OFFLINE_ROOT/.env" \
        --env-file "$OFFLINE_ROOT/versions.env" \
        --env-file "$OFFLINE_ROOT/versions.gpu.env" \
        -f "$OFFLINE_ROOT/compose.yaml" \
        -f "$OFFLINE_ROOT/compose.gpu.yaml" \
        "$@"
}

offline_accelerator() {
    local value

    value="$(
        offline_env_value CHATBOT_ACCELERATOR
    )"

    value="${value:-cpu}"

    case "$value" in
        cpu|gpu)
            printf '%s\n' "$value"
            ;;
        *)
            offline_die \
                "invalid installed accelerator: $value"
            ;;
    esac
}

offline_runtime_compose() {
    if [[ "$(offline_accelerator)" == "gpu" ]]; then
        offline_gpu_compose "$@"
    else
        offline_compose "$@"
    fi
}

offline_runtime_dir() {
    local value

    value="$(offline_env_value CHATBOT_RUNTIME_DIR)"
    value="${value:-./runtime}"

    if [[ "$value" == /* ]]; then
        printf '%s\n' "$value"
    else
        readlink -f "$OFFLINE_ROOT/$value"
    fi
}

offline_gateway_url() {
    local port

    port="$(
        offline_env_value GATEWAY_PORT
    )"

    port="${port:-18080}"

    printf 'http://127.0.0.1:%s\n' \
        "$port"
}

offline_detect_host_ip() {
    if [[ -n "${CHATBOT_HOST_IP:-}" ]]; then
        printf '%s\n' \
            "$CHATBOT_HOST_IP"
        return 0
    fi

    local candidate=""

    if command -v ip >/dev/null 2>&1; then
        candidate="$(
            ip -4 route get 1.1.1.1 \
                2>/dev/null \
            | awk '
                {
                    for (i = 1; i <= NF; i++) {
                        if ($i == "src" && (i + 1) <= NF) {
                            print $(i + 1)
                            exit
                        }
                    }
                }
            ' \
            || true
        )"

        if [[ -n "$candidate" ]]; then
            printf '%s\n' \
                "$candidate"
            return 0
        fi

        candidate="$(
            ip -o -4 addr show scope global \
                2>/dev/null \
            | awk '
                $2 !~ /^(docker|br-|veth|virbr)/ {
                    split($4, address, "/")
                    print address[1]
                    exit
                }
            ' \
            || true
        )"

        if [[ -n "$candidate" ]]; then
            printf '%s\n' \
                "$candidate"
            return 0
        fi
    fi

    if command -v hostname >/dev/null 2>&1; then
        candidate="$(
            hostname -I \
                2>/dev/null \
            | awk '{
                for (i = 1; i <= NF; i++) {
                    if ($i !~ /^127\./) {
                        print $i
                        exit
                    }
                }
            }' \
            || true
        )"

        if [[ -n "$candidate" ]]; then
            printf '%s\n' \
                "$candidate"
            return 0
        fi
    fi

    printf '%s\n' \
        "127.0.0.1"
}

offline_checksum() {
    python3 \
        "$OFFLINE_ROOT/offline/lib/check.py" \
        checksum \
        "$1"
}

offline_verify() {
    python3 \
        "$OFFLINE_ROOT/offline/lib/check.py" \
        runtime \
        "$(offline_gateway_url)" \
        "$(offline_runtime_dir)/secrets/chat_api_key"
}

offline_media_accept() {
    local figure_dir

    figure_dir="$(
        offline_env_value FIGURE_DIR
    )"

    if [[ "$figure_dir" != /* ]]; then
        figure_dir="$(
            readlink -f \
                "$OFFLINE_ROOT/$figure_dir"
        )"
    fi

    python3 \
        "$OFFLINE_ROOT/offline/lib/check.py" \
        media \
        "$(offline_gateway_url)" \
        "$(offline_runtime_dir)/secrets/chat_api_key" \
        "$figure_dir" \
        "$OFFLINE_ROOT/data/figures/heatmap1.png"
}
