#!/usr/bin/env bash
set -Eeuo pipefail

ACCELERATOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

accelerator_usage() {
  echo "usage: $0 {resolve|online} {auto|cpu|gpu} [command]" >&2
}

gpu_host_ready() {
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU support requires nvidia-smi." >&2
    return 1
  fi
  if ! nvidia-smi -L >/dev/null 2>&1; then
    echo "NVIDIA GPU support requires a working NVIDIA driver." >&2
    return 1
  fi
  if ! docker info --format '{{json .Runtimes}}' | grep -q '"nvidia"'; then
    echo "NVIDIA GPU support requires the Docker NVIDIA runtime." >&2
    return 1
  fi
}

resolve_accelerator() {
  local requested="$1"
  case "$requested" in
    cpu)
      printf '%s\n' cpu
      ;;
    gpu)
      gpu_host_ready || return 1
      printf '%s\n' gpu
      ;;
    auto)
      if gpu_host_ready; then
        printf '%s\n' gpu
      else
        echo "NVIDIA GPU support is unavailable; using the CPU profile." >&2
        printf '%s\n' cpu
      fi
      ;;
    *)
      echo "ACCELERATOR must be auto, cpu, or gpu; got: $requested" >&2
      return 2
      ;;
  esac
}

accelerator_compose_files() {
  local profile="$1"
  local base_file="$2"
  local gpu_file="$3"
  ACCELERATOR_COMPOSE_FILES=(-f "$base_file")
  if [[ "$profile" == "gpu" ]]; then
    ACCELERATOR_COMPOSE_FILES+=(-f "$gpu_file")
  fi
}

verify_gpu_container() {
  local image="$1"
  docker run --rm --gpus all "$image" --list-devices | grep -q '^  CUDA'
}

run_online_compose() {
  local profile="$1"
  shift
  accelerator_compose_files "$profile" \
    "$ACCELERATOR_ROOT/docker-compose.yml" \
    "$ACCELERATOR_ROOT/docker-compose.gpu.yml"
  if [[ "$profile" == "cpu" ]]; then
    LLAMA_GPU_LAYERS=0 LLAMA_GPU_LAYERS_DRAFT=0 EMBEDDING_GPU_LAYERS=0 \
      docker compose "${ACCELERATOR_COMPOSE_FILES[@]}" "$@"
  else
    docker compose "${ACCELERATOR_COMPOSE_FILES[@]}" "$@"
  fi
}

run_online() {
  local requested="$1"
  local action="$2"
  local profile
  profile="$(resolve_accelerator "$requested")"
  case "$action" in
    start)
      run_online_compose "$profile" build chatbot
      run_online_compose "$profile" up -d --wait \
        postgres chromadb llama-server embedding-server
      run_online_compose "$profile" run --rm --no-deps chatbot \
        python -m src.index_documents
      run_online_compose "$profile" up -d --wait chatbot
      ;;
    stop)
      run_online_compose "$profile" down
      ;;
    status)
      run_online_compose "$profile" ps
      ;;
    index)
      run_online_compose "$profile" exec chatbot python -m src.index_documents
      ;;
    *)
      echo "usage: $0 online {auto|cpu|gpu} {start|stop|status|index}" >&2
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    resolve)
      [[ $# == 2 ]] || { accelerator_usage; exit 2; }
      resolve_accelerator "$2"
      ;;
    online)
      [[ $# == 3 ]] || { accelerator_usage; exit 2; }
      run_online "$2" "$3"
      ;;
    *)
      accelerator_usage
      exit 2
      ;;
  esac
fi
