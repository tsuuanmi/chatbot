#!/usr/bin/env bash
set -Eeuo pipefail

HOST_OS_RELEASE="${HOST_OS_RELEASE:-/etc/os-release}"

host_platform() {
  [[ -r "$HOST_OS_RELEASE" ]] || {
    echo "Cannot read operating system metadata: $HOST_OS_RELEASE" >&2
    return 1
  }
  # shellcheck disable=SC1090
  source "$HOST_OS_RELEASE"
  case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:22.04|ubuntu:26.04)
      printf '%s\n' ubuntu
      ;;
    rhel:8.10)
      printf '%s\n' rhel
      ;;
    *)
      echo "Unsupported target operating system: ${PRETTY_NAME:-${ID:-unknown} ${VERSION_ID:-unknown}}" >&2
      echo "Supported offline targets: Ubuntu 22.04, Ubuntu 26.04, and Red Hat Enterprise Linux 8.10." >&2
      return 1
      ;;
  esac
}

host_firewall_backend() {
  case "$1" in
    ubuntu) printf '%s\n' ufw ;;
    rhel) printf '%s\n' firewalld ;;
    *)
      echo "Unsupported host platform: $1" >&2
      return 2
      ;;
  esac
}

verify_host_python() {
  python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version'
}

validate_host_platform() {
  local platform="$1"
  verify_host_python || {
    echo "Offline installation requires Python 3.9 or newer." >&2
    return 1
  }
  if [[ "$platform" == rhel ]]; then
    command -v getenforce >/dev/null 2>&1 || {
      echo "RHEL installation requires SELinux tools (getenforce)." >&2
      return 1
    }
    [[ "$(getenforce)" == "Enforcing" ]] || {
      echo "RHEL installation requires SELinux Enforcing; do not disable SELinux." >&2
      return 1
    }
  fi
}
