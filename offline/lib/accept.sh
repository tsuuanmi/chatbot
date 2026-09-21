#!/usr/bin/env bash

offline_accept() {
    offline_require_installation

    offline_require_command docker
    offline_require_command python3

    [[ -f "$OFFLINE_ROOT/BUNDLE-MANIFEST.txt" ]] ||
        offline_die \
            "accept requires a built offline bundle with BUNDLE-MANIFEST.txt; use 'make accept' for source-tree acceptance"

    local architecture

    architecture="$(
        offline_manifest_value \
            "$OFFLINE_ROOT/BUNDLE-MANIFEST.txt" \
            architecture
    )"

    [[ -n "$architecture" ]] ||
        offline_die \
            "Bundle architecture is missing"

    [[ "$architecture" == "$(uname -m)" ]] ||
        offline_die \
            "Bundle architecture $architecture does not match host $(uname -m)"

    echo \
        "PASS architecture=$architecture"

    [[ -f /etc/os-release ]] ||
        offline_die \
            "/etc/os-release is missing"

    local platform_id

    platform_id="$(
        (
            # shellcheck disable=SC1091
            source /etc/os-release
            printf '%s\n' "${ID:-}"
        )
    )"

    case "$platform_id" in
        ubuntu)
            echo \
                "PASS platform=ubuntu"
            ;;

        rhel|rocky|almalinux|centos)
            offline_require_command getenforce

            local selinux_mode
            selinux_mode="$(getenforce)"

            [[ "$selinux_mode" == "Enforcing" ]] ||
                offline_die \
                    "RHEL-compatible deployment requires SELinux Enforcing"

            echo \
                "PASS platform=$platform_id selinux=Enforcing"
            ;;

        *)
            offline_die \
                "Unsupported acceptance platform: $platform_id"
            ;;
    esac

    offline_compose config >/dev/null

    echo \
        "PASS compose configuration"

    local service
    local container_id
    local status

    for service in \
        postgres \
        llama-server \
        chatbot \
        proxy
    do
        container_id="$(
            offline_compose ps -q "$service"
        )"

        [[ -n "$container_id" ]] ||
            offline_die \
                "Service is not running: $service"

        status="$(
            docker inspect \
                --format \
                '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
                "$container_id"
        )"

        [[ "$status" == "healthy" ]] ||
            offline_die \
                "Service is not healthy: $service status=$status"

        echo \
            "PASS service=$service status=$status"
    done

    local chatbot_id
    local proxy_id

    chatbot_id="$(
        offline_compose ps -q chatbot
    )"

    proxy_id="$(
        offline_compose ps -q proxy
    )"

    local chatbot_user

    chatbot_user="$(
        docker inspect \
            --format '{{.Config.User}}' \
            "$chatbot_id"
    )"

    [[ "$chatbot_user" == "10001:10001" ]] ||
        offline_die \
            "Unexpected chatbot user: $chatbot_user"

    echo \
        "PASS chatbot non-root user=$chatbot_user"

    [[ "$(
        docker inspect \
            --format '{{.HostConfig.ReadonlyRootfs}}' \
            "$chatbot_id"
    )" == "true" ]] ||
        offline_die \
            "Chatbot root filesystem is not read-only"

    echo \
        "PASS chatbot read-only filesystem"

    [[ "$(
        docker inspect \
            --format '{{.HostConfig.ReadonlyRootfs}}' \
            "$proxy_id"
    )" == "true" ]] ||
        offline_die \
            "Proxy root filesystem is not read-only"

    echo \
        "PASS proxy read-only filesystem"

    local published

    published="$(
        docker port \
            "$chatbot_id" \
            1416/tcp \
            2>/dev/null \
            || true
    )"

    [[ -z "$published" ]] ||
        offline_die \
            "Production chatbot port 1416 is published"

    echo \
        "PASS chatbot private network boundary"

    offline_host_accept

    offline_verify
    offline_media_accept

    echo
    echo \
        "OFFLINE PLATFORM ACCEPTANCE PASS"
}
