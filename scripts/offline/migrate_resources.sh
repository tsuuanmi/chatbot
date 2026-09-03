#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
usage: migrate_resources.sh --confirm [--container NAME_OR_ID]... [--volume NAME]...

Remove explicitly named Docker containers and volumes left by an earlier deployment.
Names are literal resource names; wildcards and automatic discovery are not supported.
EOF
}

confirmed=false
containers=()
volumes=()
while (( $# > 0 )); do
  case "$1" in
    --confirm)
      confirmed=true
      shift
      ;;
    --container)
      [[ -n "${2:-}" ]] || { echo "--container requires a name or ID" >&2; exit 2; }
      containers+=("$2")
      shift 2
      ;;
    --volume)
      [[ -n "${2:-}" ]] || { echo "--volume requires a name" >&2; exit 2; }
      volumes+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$confirmed" != true ]]; then
  echo "Refusing to remove Docker resources without --confirm." >&2
  exit 2
fi
if (( ${#containers[@]} == 0 && ${#volumes[@]} == 0 )); then
  echo "Specify at least one --container or --volume." >&2
  exit 2
fi

for resource in "${containers[@]}" "${volumes[@]}"; do
  [[ "$resource" =~ ^[[:alnum:]][[:alnum:]_.-]*$ ]] || {
    echo "Invalid Docker resource name or ID: $resource" >&2
    exit 2
  }
done

command -v docker >/dev/null 2>&1 || {
  echo "Required command not found: docker" >&2
  exit 1
}

if (( ${#containers[@]} > 0 )); then
  printf 'Removing %d explicitly selected container(s)\n' "${#containers[@]}"
  docker rm -f "${containers[@]}"
fi
if (( ${#volumes[@]} > 0 )); then
  printf 'Removing %d explicitly selected volume(s)\n' "${#volumes[@]}"
  docker volume rm "${volumes[@]}"
fi
