#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/compose/docker-compose.offline.yml" ]]; then
  INSTALL_DIR="$SCRIPT_DIR"
else
  INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
MODEL_DIR="$INSTALL_DIR/models"
IMAGES_DIR="$INSTALL_DIR/images"
BIND_ADDRESS="${BIND_ADDRESS:-0.0.0.0}"
SERVER_ADDRESS="${SERVER_ADDRESS:-}"
LAN_CIDR="${LAN_CIDR:-}"
HTTP_PORT="${HTTP_PORT:-80}"
SSH_PORT="${SSH_PORT:-22}"
CLIENT_COUNT="${CLIENT_COUNT:-5}"
GPU=""
MODE="offline"
ACCELERATOR=""
ZIP_DIR="${ZIP_DIR:-}"
CHATBOT_ZIP=""
IMAGES_ZIP=""
MODELS_ZIP=""
HAVE_IMAGES_ZIP=false
HAVE_MODELS_ZIP=false
REINSTALL=false
INSTALL_MARKER="$INSTALL_DIR/config/.installed"
INSTALL_LOG="$INSTALL_DIR/install.log"
installation_started=false
installation_complete=false
reset_incomplete_installation=false
stopped_incomplete_gpu_containers=()
image_archive_entries=()
archive_names=()
step_number=0
current_step="initialization"
total_steps=19
readonly residual_gpu_limit_mb=1024
readonly minimum_gpu_memory_mib=6144

command -v tee >/dev/null 2>&1 || {
  echo "Missing prerequisite: tee" >&2
  exit 1
}
touch "$INSTALL_LOG"
chmod 600 "$INSTALL_LOG"
exec > >(tee -a "$INSTALL_LOG") 2>&1

log() {
  printf '[install %(%Y-%m-%dT%H:%M:%S%z)T] %s\n' -1 "$*"
}

is_chatbot_project_identity() {
  local identity="$1"
  [[ "$identity" == "$CHATBOT_PROJECT_NAME" ]]
}

add_chatbot_volume() {
  local candidate="$1" existing_volume
  for existing_volume in "${chatbot_volumes[@]}"; do
    [[ "$candidate" == "$existing_volume" ]] && return 0
  done
  chatbot_volumes+=("$candidate")
}

stop_incomplete_gpu_containers() {
  local container_id compose_project
  local existing_container_output
  existing_container_output="$(docker ps -q)"
  [[ -n "$existing_container_output" ]] || return 0
  while IFS= read -r container_id; do
    compose_project="$(docker inspect --format '{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{end}}' "$container_id")"
    if is_chatbot_project_identity "$compose_project"; then
      log "Stopping interrupted chatbot GPU container before residual GPU validation: $container_id"
      docker stop "$container_id" >/dev/null
      stopped_incomplete_gpu_containers+=("$container_id")
    fi
  done <<< "$existing_container_output"
}

print_startup_diagnostics() {
  log "Service startup failed; printing status and diagnostic logs before rollback"
  compose ps >&2 || true
  compose logs --tail=200 \
    postgres chromadb llama-server embedding-server chatbot proxy >&2 || true
}

verify_models() {
  local required_models=(
    gemma-4-E2B-it-Q4_K_M.gguf
    mmproj-gemma-4-E2B-it-bf16.gguf
    mtp-gemma-4-E2B-it.gguf
    embeddinggemma-300M-Q8_0.gguf
  )
  for model in "${required_models[@]}"; do
    [[ -f "$MODEL_DIR/$model" ]] || {
      echo "Missing model: $MODEL_DIR/$model" >&2
      echo "Extract models.zip into $MODEL_DIR or place all four GGUF files there, then run setup.sh again." >&2
      return 1
    }
    log "Found model filename: $model"
  done
  if [[ -f "$MODEL_DIR/SHA256SUMS" ]]; then
    (cd "$MODEL_DIR" && sha256sum -c SHA256SUMS)
  fi
}

zip_has_member() {
  unzip -l "$1" "$2" >/dev/null 2>&1
}

image_archive_matches() {
  local archive="$1" expected_sha256="$2" actual_sha256
  [[ -f "$IMAGES_DIR/$archive" ]] || return 1
  actual_sha256="$(sha256sum "$IMAGES_DIR/$archive")"
  actual_sha256="${actual_sha256%% *}"
  [[ "$actual_sha256" == "$expected_sha256" ]]
}

docker_image_id() {
  docker image inspect --format '{{.Id}}' "$1" 2>/dev/null || true
}

verify_source_matches_chatbot_zip() {
  local verified=0 member relative folder_file zip_sha256 folder_sha256
  while IFS= read -r member; do
    case "$member" in
      chatbot/SHA256SUMS|chatbot/release-manifest.json) continue ;;
      chatbot/setup.sh)
        [[ -f "$INSTALL_DIR/setup.sh" ]] || continue
        relative="setup.sh" ;;
      chatbot/*) relative="${member#chatbot/}" ;;
      *) continue ;;
    esac
    folder_file="$INSTALL_DIR/$relative"
    if [[ ! -f "$folder_file" ]]; then
      echo "chatbot folder does not match chatbot.zip: missing $relative" >&2
      echo "Unzip the current chatbot.zip over $INSTALL_DIR and run setup.sh again." >&2
      return 1
    fi
    zip_sha256="$(unzip -p "$CHATBOT_ZIP" "$member" | sha256sum)"
    zip_sha256="${zip_sha256%% *}"
    folder_sha256="$(sha256sum "$folder_file")"
    folder_sha256="${folder_sha256%% *}"
    if [[ "$zip_sha256" != "$folder_sha256" ]]; then
      echo "chatbot folder does not match chatbot.zip: $relative differs" >&2
      echo "Unzip the current chatbot.zip over $INSTALL_DIR (or rebuild the release" >&2
      echo "from the matching source commit) and run setup.sh again." >&2
      return 1
    fi
    verified=$((verified + 1))
  done < <(unzip -Z1 "$CHATBOT_ZIP" | grep -v '/$')
  log "Verified $verified source files in the chatbot folder match chatbot.zip"
}

read_image_archives() {
  python3 - "$INSTALL_DIR/release-manifest.json" <<'PY'
import json
import re
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
archives = manifest.get("image_archives")
if not isinstance(archives, list) or not archives:
    raise SystemExit(
        "release-manifest.json has no image_archives; rebuild all release ZIPs"
        " with one make prepare run and transfer them together"
    )
for entry in archives:
    values = {}
    for field in ("image", "archive", "archive_sha256", "image_id"):
        value = entry.get(field) if isinstance(entry, dict) else None
        if not isinstance(value, str) or not value:
            raise SystemExit(f"release manifest image archive entry is missing {field}")
        values[field] = value
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", values["archive"]):
        raise SystemExit(
            f"release manifest image archive has an invalid name: {values['archive']}"
        )
    if len(values["archive_sha256"]) != 64:
        raise SystemExit(
            f"release manifest image archive has an invalid checksum: {values['archive']}"
        )
    print(
        "\t".join(
            (
                values["image"],
                values["archive"],
                values["archive_sha256"],
                values["image_id"],
            )
        )
    )
PY
}

replenish_image_archives() {
  local entry archive_image archive_name archive_sha256 archive_image_id
  local image_archives_output
  local -a unavailable_archives=()
  image_archives_output="$(read_image_archives)"
  mapfile -t image_archive_entries <<< "$image_archives_output"
  for entry in "${image_archive_entries[@]}"; do
    IFS=$'\t' read -r archive_image archive_name archive_sha256 archive_image_id <<< "$entry"
    archive_names+=("$archive_name")
    if image_archive_matches "$archive_name" "$archive_sha256"; then
      continue
    fi
    if [[ "$HAVE_IMAGES_ZIP" == true ]] \
      && zip_has_member "$IMAGES_ZIP" "chatbot/images/$archive_name"; then
      log "Extracting new image archive: images/$archive_name"
      unzip -o -j "$IMAGES_ZIP" "chatbot/images/$archive_name" -d "$IMAGES_DIR" >/dev/null
      image_archive_matches "$archive_name" "$archive_sha256" || {
        echo "image archive checksum does not match the release manifest: images/$archive_name" >&2
        exit 1
      }
    else
      unavailable_archives+=("$archive_name")
    fi
  done
  if (( ${#unavailable_archives[@]} > 0 )); then
    log "Image archives not available yet: ${unavailable_archives[*]}"
    log "They are required only for images missing from Docker; the installer reports any that are needed"
  fi
}

prune_stale_archives() {
  local archive_path archive_name known_name found stale
  local -a stale_archives=()
  for archive_path in "$IMAGES_DIR"/*.tar; do
    [[ -f "$archive_path" ]] || continue
    archive_name="$(basename "$archive_path")"
    found=false
    for known_name in "${archive_names[@]}"; do
      [[ "$archive_name" == "$known_name" ]] && { found=true; break; }
    done
    [[ "$found" == true ]] || stale_archives+=("$archive_name")
  done
  for stale in "${stale_archives[@]}"; do
    log "Removing stale image archive: images/$stale"
    rm -f "$IMAGES_DIR/$stale"
  done
}

models_match_checksums() {
  local checksums="$1" line expected_sha256 model_name actual_sha256
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    expected_sha256="${line%% *}"
    model_name="${line##* }"
    [[ -f "$MODEL_DIR/$model_name" ]] || return 1
    actual_sha256="$(sha256sum "$MODEL_DIR/$model_name")"
    actual_sha256="${actual_sha256%% *}"
    [[ "$actual_sha256" == "$expected_sha256" ]] || return 1
  done <<< "$checksums"
}

replenish_models() {
  local checksums
  if [[ "$HAVE_MODELS_ZIP" == true ]]; then
    checksums="$(unzip -p "$MODELS_ZIP" chatbot/models/SHA256SUMS)"
    if models_match_checksums "$checksums"; then
      log "Models already match models.zip; skipping extraction"
      unzip -p "$MODELS_ZIP" chatbot/models/SHA256SUMS > "$MODEL_DIR/SHA256SUMS"
    else
      log "Extracting model files from models.zip"
      unzip -o -j "$MODELS_ZIP" 'chatbot/models/*' -d "$MODEL_DIR" >/dev/null
    fi
  elif [[ -f "$MODEL_DIR/SHA256SUMS" ]]; then
    log "models.zip not provided; verifying existing model files"
  else
    echo "models.zip was not found in $ZIP_DIR and $MODEL_DIR/SHA256SUMS is missing." >&2
    echo "Copy models.zip into $ZIP_DIR or place verified GGUF files in $MODEL_DIR." >&2
    exit 1
  fi
}

load_manifest_images() {
  local entry archive_image archive_name archive_sha256 archive_image_id loaded_image_id
  for entry in "${image_archive_entries[@]}"; do
    IFS=$'\t' read -r archive_image archive_name archive_sha256 archive_image_id <<< "$entry"
    if [[ "$(docker_image_id "$archive_image")" == "$archive_image_id" ]]; then
      log "Image already present and unchanged, skipping load: $archive_image"
      continue
    fi
    if [[ -f "$IMAGES_DIR/$archive_name" ]] \
      && ! image_archive_matches "$archive_name" "$archive_sha256"; then
      echo "images/$archive_name does not match release-manifest.json;" >&2
      echo "chatbot.zip and the image archives must come from one make prepare run." >&2
      exit 1
    fi
    if ! image_archive_matches "$archive_name" "$archive_sha256"; then
      echo "Docker image is missing and images/$archive_name was not found." >&2
      echo "Copy the updated images/$archive_name into $IMAGES_DIR or provide images.zip" >&2
      echo "in $ZIP_DIR, then run setup.sh again." >&2
      exit 1
    fi
    log "Loading image: $archive_image"
    docker load -i "$IMAGES_DIR/$archive_name" >/dev/null
    loaded_image_id="$(docker_image_id "$archive_image")"
    [[ "$loaded_image_id" == "$archive_image_id" ]] || {
      echo "Loaded image does not match the release manifest: $archive_image" >&2
      exit 1
    }
  done
}

remove_legacy_images() {
  local image_ref repository expected found
  local -a current_images=() managed_repositories=() docker_refs=()
  local current_images_output docker_refs_output
  current_images_output="$(python3 -c \
    'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["images"]))' \
    "$INSTALL_DIR/release-manifest.json")"
  mapfile -t current_images <<< "$current_images_output"
  managed_repositories=()
  for image_ref in "${current_images[@]}"; do
    repository="${image_ref%:*}"
    found=false
    for expected in "${managed_repositories[@]}"; do
      [[ "$repository" == "$expected" ]] && { found=true; break; }
    done
    [[ "$found" == true ]] || managed_repositories+=("$repository")
  done
  docker_refs_output="$(docker images --format '{{.Repository}}:{{.Tag}}')"
  mapfile -t docker_refs <<< "$docker_refs_output"
  for image_ref in "${docker_refs[@]}"; do
    repository="${image_ref%:*}"
    found=false
    for expected in "${managed_repositories[@]}"; do
      [[ "$repository" == "$expected" ]] && { found=true; break; }
    done
    [[ "$found" == true ]] || continue
    found=false
    for expected in "${current_images[@]}"; do
      [[ "$image_ref" == "$expected" ]] && { found=true; break; }
    done
    [[ "$found" == true ]] && continue
    if docker rmi "$image_ref" >/dev/null 2>&1; then
      log "Removed legacy chatbot image: $image_ref"
    else
      log "Kept legacy chatbot image still in use: $image_ref"
    fi
  done
}

step() {
  step_number=$((step_number + 1))
  current_step="$*"
  log "STEP $step_number/$total_steps: $current_step"
}

report_error() {
  local status=$?
  log "ERROR during '$current_step' at line ${BASH_LINENO[0]}: $BASH_COMMAND"
  return "$status"
}
trap report_error ERR

usage() {
  echo "usage: $0 --gpu yes|no [--mode offline|online] [--reinstall] [--zip-dir DIR]" >&2
  echo "optional environment: SERVER_ADDRESS, LAN_CIDR, BIND_ADDRESS, HTTP_PORT, SSH_PORT, CLIENT_COUNT, ZIP_DIR" >&2
}

while (( $# != 0 )); do
  case "$1" in
    --gpu)
      [[ -n "${2:-}" ]] || { echo "--gpu requires an argument" >&2; usage; exit 2; }
      GPU="$2"; shift 2 ;;
    --gpu=*)
      GPU="${1#--gpu=}"; shift ;;
    --mode)
      [[ -n "${2:-}" ]] || { echo "--mode requires an argument" >&2; usage; exit 2; }
      MODE="$2"; shift 2 ;;
    --mode=*)
      MODE="${1#--mode=}"; shift ;;
    --reinstall)
      REINSTALL=true
      shift ;;
    --zip-dir)
      [[ -n "${2:-}" ]] || { echo "--zip-dir requires an argument" >&2; usage; exit 2; }
      ZIP_DIR="$2"; shift 2 ;;
    --zip-dir=*)
      ZIP_DIR="${1#--zip-dir=}"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done
[[ "$GPU" == "yes" || "$GPU" == "no" ]] || {
  echo "--gpu must be yes or no" >&2
  usage
  exit 2
}
[[ "$MODE" == "offline" || "$MODE" == "online" ]] || {
  echo "--mode must be offline or online" >&2
  usage
  exit 2
}
if [[ -z "$ZIP_DIR" ]]; then
  ZIP_DIR="$(cd "$INSTALL_DIR/.." && pwd)"
fi
CHATBOT_ZIP="$ZIP_DIR/chatbot.zip"
IMAGES_ZIP="$ZIP_DIR/images.zip"
MODELS_ZIP="$ZIP_DIR/models.zip"
if [[ "$GPU" == "yes" ]]; then
  ACCELERATOR="gpu"
else
  ACCELERATOR="cpu"
fi
if [[ "$MODE" == "online" ]]; then
  total_steps=4
fi

cleanup_incomplete_installation() {
  local cleanup_status=0
  log "Removing generated state from the incomplete installation"
  if [[ -f "$INSTALL_DIR/.env" ]]; then
    export OFFLINE_ENV="$INSTALL_DIR/.env"
    # shellcheck source=common.sh
    source "$INSTALL_DIR/scripts/offline/common.sh"
    compose stop proxy chatbot chromadb >/dev/null 2>&1 || cleanup_status=1
    compose run --rm --no-deps --entrypoint bash chromadb \
      -c 'rm -rf /data/* /data/.[!.]* /data/..?*' \
      >/dev/null 2>&1 || cleanup_status=1
    compose down -v --remove-orphans >/dev/null 2>&1 || cleanup_status=1
  fi
  if (( cleanup_status != 0 )); then
    log "Cleanup failed; retaining .env and credentials for operator recovery"
    return "$cleanup_status"
  fi
  rm -f "$INSTALL_DIR/.env" "$INSTALL_MARKER"
  rm -rf "$INSTALL_DIR/config/auth" "$INSTALL_DIR/config/clients" \
    "$INSTALL_DIR/config/tls"
  mkdir -p "$INSTALL_DIR/runtime/chromadb"
}

rollback_incomplete_installation() {
  local status=$?
  if (( status != 0 )) && (( ${#stopped_incomplete_gpu_containers[@]} > 0 )); then
    log "Restoring interrupted chatbot GPU containers after preflight failure"
    docker start "${stopped_incomplete_gpu_containers[@]}" >/dev/null \
      || log "Could not restore all interrupted chatbot GPU containers"
  fi
  if (( status != 0 )) && [[ "$installation_started" == true ]] \
    && [[ "$installation_complete" != true ]]; then
    log "Installation failed; rolling back generated chatbot state for a safe retry"
    if ! cleanup_incomplete_installation; then
      log "Automatic rollback was incomplete; preserve this folder for recovery"
    fi
    log "Removed selected chatbot containers and volumes are not restored; host firewall rules may remain active"
  fi
  return "$status"
}
trap rollback_incomplete_installation EXIT

step "Validate installer arguments and prerequisites"
if [[ "$MODE" == "online" ]]; then
  required_commands=(docker sha256sum)
else
  # shellcheck source=offline/host_platform.sh
  source "$INSTALL_DIR/scripts/offline/host_platform.sh"
  HOST_PLATFORM="$(host_platform)"
  HOST_FIREWALL="$(host_firewall_backend "$HOST_PLATFORM")"
  if [[ "$HOST_FIREWALL" == "firewalld" ]]; then
    firewall_command=firewall-cmd
  else
    firewall_command="$HOST_FIREWALL"
  fi
  required_commands=(awk curl docker ip openssl python3 sha256sum sudo systemctl iptables unzip "$firewall_command")
fi
for command in "${required_commands[@]}"; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing prerequisite: $command" >&2
    exit 1
  }
done
project_digest="$(printf '%s' "$INSTALL_DIR" | sha256sum)"
project_digest="${project_digest%% *}"
CHATBOT_PROJECT_NAME="chatbot-${project_digest:0:12}"
docker compose version >/dev/null
if [[ "$MODE" == "offline" ]]; then
  validate_host_platform "$HOST_PLATFORM"
  log "Supported target platform: $HOST_PLATFORM ($HOST_FIREWALL firewall backend)"
fi
[[ "$(uname -m)" == "x86_64" ]] || {
  echo "chatbot.zip requires an x86_64 target computer." >&2
  exit 1
}
if [[ "$MODE" == "offline" ]]; then
  [[ "$CLIENT_COUNT" =~ ^[0-9]+$ ]] \
    && (( CLIENT_COUNT >= 1 && CLIENT_COUNT <= 99 )) || {
    echo "CLIENT_COUNT must be an integer from 1 through 99." >&2
    exit 1
  }
  if [[ -e "$INSTALL_MARKER" && "$REINSTALL" != true ]]; then
    echo "This folder is already configured." >&2
    echo "Pass --reinstall to wipe and reinstall it (fresh database and new client" >&2
    echo "keys), or start the installed stack with ./scripts/offline/offline.sh start." >&2
    exit 1
  fi
  if [[ "$REINSTALL" == true ]]; then
    rm -f "$INSTALL_MARKER"
  fi
  if [[ -e "$INSTALL_DIR/.env" ]]; then
    [[ "${RESET_INCOMPLETE_INSTALL:-}" == "YES" || "$REINSTALL" == true ]] || {
      echo "An incomplete installation was found." >&2
      echo "Re-run with RESET_INCOMPLETE_INSTALL=YES or --reinstall to reset and retry." >&2
      exit 1
    }
    reset_incomplete_installation=true
  fi
  [[ -f "$INSTALL_DIR/compose/docker-compose.offline.yml" \
    && -f "$INSTALL_DIR/compose/docker-compose.offline.gpu.yml" \
    && -f "$INSTALL_DIR/scripts/accelerator.sh" \
    && -f "$INSTALL_DIR/scripts/offline/configure_host.sh" \
    && -f "$INSTALL_DIR/scripts/offline/host_platform.sh" \
    && -f "$INSTALL_DIR/scripts/offline/detect_network.py" \
    && -f "$INSTALL_DIR/scripts/offline/common.sh" \
    && -f "$INSTALL_DIR/scripts/offline/manage_client.sh" \
    && -f "$INSTALL_DIR/config/offline.env.template" ]] || {
    echo "chatbot.zip entry files are missing from $INSTALL_DIR." >&2
    echo "Unzip chatbot.zip into $ZIP_DIR before running setup.sh." >&2
    exit 1
  }
  [[ -f "$CHATBOT_ZIP" ]] || {
    echo "Required release archive not found: $CHATBOT_ZIP" >&2
    echo "Copy chatbot.zip into $ZIP_DIR or pass --zip-dir / ZIP_DIR." >&2
    exit 1
  }
  log "Release ZIP directory: $ZIP_DIR"
else
  [[ -f "$INSTALL_DIR/compose/docker-compose.yml" \
    && -f "$INSTALL_DIR/compose/docker-compose.gpu.yml" \
    && -f "$INSTALL_DIR/scripts/accelerator.sh" \
    && -f "$INSTALL_DIR/.env.example" ]] || {
    echo "Required online files are missing or incomplete." >&2
    exit 1
  }
fi
# shellcheck source=accelerator.sh
source "$INSTALL_DIR/scripts/accelerator.sh"
if [[ "$ACCELERATOR" == "gpu" ]] && ! gpu_host_ready; then
  exit 1
fi
log "All required host commands and release entry files are present"
log "Selected accelerator profile: $ACCELERATOR"
if [[ "$MODE" == "offline" ]]; then
  log "Requesting administrator access required for automatic firewall setup"
  sudo -v
fi

if [[ "$MODE" == "online" ]]; then
  step "Verify GGUF model files"
  verify_models
  step "Prepare online configuration"
  if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    log "Copied .env.example to .env"
  else
    log "Using existing .env"
  fi
  step "Start the online chatbot stack"
  "$INSTALL_DIR/scripts/accelerator.sh" online "$ACCELERATOR" start
  installation_complete=true
  log "Online chatbot stack is ready: $INSTALL_DIR"
  exit 0
fi

step "Verify release ZIP archives"
unzip -tq "$CHATBOT_ZIP" >/dev/null
log "Verified archive integrity: chatbot.zip"
if [[ -f "$IMAGES_ZIP" ]]; then
  HAVE_IMAGES_ZIP=true
  unzip -tq "$IMAGES_ZIP" >/dev/null
  log "Verified archive integrity: images.zip"
else
  log "images.zip not provided; existing $IMAGES_DIR content will be verified"
fi
if [[ -f "$MODELS_ZIP" ]]; then
  HAVE_MODELS_ZIP=true
  unzip -tq "$MODELS_ZIP" >/dev/null
  log "Verified archive integrity: models.zip"
else
  log "models.zip not provided; existing $MODEL_DIR content will be verified"
fi

step "Verify the chatbot folder matches chatbot.zip"
unzip -p "$CHATBOT_ZIP" chatbot/SHA256SUMS > "$INSTALL_DIR/SHA256SUMS"
unzip -p "$CHATBOT_ZIP" chatbot/release-manifest.json > "$INSTALL_DIR/release-manifest.json"
log "Refreshed SHA256SUMS and release-manifest.json from chatbot.zip"
verify_source_matches_chatbot_zip

step "Replenish image archives and model files"
mkdir -p "$IMAGES_DIR"
replenish_image_archives
prune_stale_archives
replenish_models

step "Detect the primary LAN address and subnet"
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

step "Verify release files, model filenames, and free space"
verify_models
(
  cd "$INSTALL_DIR"
  sha256sum -c SHA256SUMS --ignore-missing
)
available_kb="$(df -Pk "$INSTALL_DIR" | awk 'NR==2 {print $4}')"
required_kb=$((20 * 1024 * 1024))
if (( available_kb < required_kb )); then
  echo "At least 20 GB free space is required in $INSTALL_DIR." >&2
  exit 1
fi
log "Release checksums passed; at least 20 GB free space is available"

step "Load only missing or changed Docker images and verify required tags"
python3 - "$INSTALL_DIR/release-manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if manifest.get("architecture") != "x86_64":
    raise SystemExit(f"unsupported archive architecture: {manifest.get('architecture')}")
images = manifest.get("images")
accelerator_images = manifest.get("accelerator_images")
if not isinstance(images, list) or not isinstance(accelerator_images, dict):
    raise SystemExit("release manifest is missing image metadata")
for profile in ("cpu", "gpu"):
    image = accelerator_images.get(profile)
    if not isinstance(image, str) or image not in images:
        raise SystemExit(f"release manifest has invalid {profile} accelerator image")
PY
LLAMA_CPU_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["accelerator_images"]["cpu"])' "$INSTALL_DIR/release-manifest.json")"
LLAMA_GPU_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["accelerator_images"]["gpu"])' "$INSTALL_DIR/release-manifest.json")"
load_manifest_images
if [[ "$ACCELERATOR" == "gpu" ]] && ! verify_gpu_container "$LLAMA_GPU_IMAGE"; then
  echo "CUDA container validation failed for $LLAMA_GPU_IMAGE." >&2
  exit 1
fi
if [[ "$ACCELERATOR" == "gpu" ]]; then
  if ! gpu_total_memory_output="$(
    nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>&1
  )"; then
    echo "Could not measure NVIDIA GPU total memory:" >&2
    echo "$gpu_total_memory_output" >&2
    exit 1
  fi
  if ! awk -v minimum="$minimum_gpu_memory_mib" '
    {
      value = $0
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value !~ /^[0-9]+([.][0-9]+)?$/ || value < minimum) exit 1
      count += 1
    }
    END { if (count == 0) exit 1 }
  ' <<< "$gpu_total_memory_output"; then
    echo "The GPU profile requires at least ${minimum_gpu_memory_mib} MiB on every NVIDIA GPU." >&2
    echo "$gpu_total_memory_output" >&2
    exit 1
  fi
fi
log "Required image tags are available for the $ACCELERATOR profile"

step "Preflight host firewall prerequisites"
"$INSTALL_DIR/scripts/offline/configure_host.sh" --preflight \
  "$LAN_CIDR" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" "$NETWORK_INTERFACE"
if [[ "$reset_incomplete_installation" == true && "$ACCELERATOR" == "gpu" ]]; then
  stop_incomplete_gpu_containers
fi

if [[ "$ACCELERATOR" == "gpu" ]]; then
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
fi

step "Validate the selected bind address and HTTP port"
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

if [[ "$reset_incomplete_installation" == true ]]; then
  stopped_incomplete_gpu_containers=()
  cleanup_incomplete_installation
fi

step "Remove existing chatbot containers and volumes"
existing_container_output="$(docker ps -aq)"
existing_containers=()
chatbot_containers=()
chatbot_volumes=()
if [[ -n "$existing_container_output" ]]; then
  mapfile -t existing_containers <<< "$existing_container_output"
fi
if (( ${#existing_containers[@]} == 0 )); then
  log "No pre-existing Docker containers found"
else
  for container_id in "${existing_containers[@]}"; do
    container_name="$(docker inspect --format '{{.Name}}' "$container_id")"
    container_name="${container_name#/}"
    compose_project="$(docker inspect --format '{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{end}}' "$container_id")"
    if is_chatbot_project_identity "$compose_project"; then
      chatbot_containers+=("$container_id")
      container_volume_output="$(docker inspect --format '{{range .Mounts}}{{if eq .Type "volume"}}{{println .Name}}{{end}}{{end}}' "$container_id")"
      if [[ -n "$container_volume_output" ]]; then
        while IFS= read -r volume; do
          add_chatbot_volume "$volume"
        done <<< "$container_volume_output"
      fi
      log "Selected chatbot container for removal: $container_name ($container_id)"
    else
      log "Preserving unrelated container: $container_name ($container_id)"
    fi
  done
fi

existing_volume_output="$(docker volume ls -q)"
existing_volumes=()
if [[ -n "$existing_volume_output" ]]; then
  mapfile -t existing_volumes <<< "$existing_volume_output"
fi
for volume in "${existing_volumes[@]}"; do
  volume_project="$(docker volume inspect --format '{{if .Labels}}{{index .Labels "com.docker.compose.project"}}{{end}}' "$volume")"
  if is_chatbot_project_identity "$volume_project"; then
    add_chatbot_volume "$volume"
  fi
done

if (( ${#chatbot_containers[@]} > 0 )); then
  log "Force-removing ${#chatbot_containers[@]} chatbot container(s)"
  docker rm -f "${chatbot_containers[@]}" >/dev/null
else
  log "No existing chatbot containers matched this deployment's Compose project label"
fi
if (( ${#chatbot_volumes[@]} > 0 )); then
  log "Removing ${#chatbot_volumes[@]} chatbot Docker volume(s) for a fresh installation"
  docker volume rm "${chatbot_volumes[@]}" >/dev/null
else
  log "No existing chatbot Docker volumes matched"
fi
rm -f "$INSTALL_DIR/config/.protected-volumes"

step "Remove legacy chatbot images from previous releases"
remove_legacy_images

step "Generate runtime configuration and service secrets"
mkdir -p "$INSTALL_DIR/runtime/chromadb" "$INSTALL_DIR/config/auth" \
  "$INSTALL_DIR/config/clients" "$INSTALL_DIR/backups"
chmod 755 "$INSTALL_DIR/runtime" "$INSTALL_DIR/runtime/chromadb"
chmod 750 "$INSTALL_DIR/config" "$INSTALL_DIR/config/auth"
chmod 700 "$INSTALL_DIR/config/clients" "$INSTALL_DIR/backups"
llama_key="$(openssl rand -hex 32)"
embedding_key="$(openssl rand -hex 32)"
postgres_password="$(openssl rand -hex 32)"
app_image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["app_image"])' "$INSTALL_DIR/release-manifest.json")"
if [[ "$ACCELERATOR" == "gpu" ]]; then
  llama_gpu_layers=16
  llama_gpu_layers_draft=0
  embedding_gpu_layers=99
else
  llama_gpu_layers=0
  llama_gpu_layers_draft=0
  embedding_gpu_layers=0
fi
installation_started=true
python3 - "$INSTALL_DIR/config/offline.env.template" "$INSTALL_DIR/.env" \
  "$INSTALL_DIR" "$BIND_ADDRESS" "$SERVER_ADDRESS" "$HTTP_PORT" "$(id -g)" \
  "$app_image" "$llama_key" "$embedding_key" "$postgres_password" \
  "$ACCELERATOR" "$LLAMA_CPU_IMAGE" "$LLAMA_GPU_IMAGE" "$llama_gpu_layers" \
  "$llama_gpu_layers_draft" "$embedding_gpu_layers" <<'PY'
import sys
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8")
origin = f"http://{sys.argv[5]}"
if sys.argv[6] != "80":
    origin = f"{origin}:{sys.argv[6]}"
replacements = {
    "__INSTALL_DIR__": sys.argv[3],
    "BIND_ADDRESS=0.0.0.0": f"BIND_ADDRESS={sys.argv[4]}",
    "CORS_ORIGINS=http://__SERVER_ADDRESS__": f"CORS_ORIGINS={origin}",
    "__SERVER_ADDRESS__": sys.argv[5],
    "HTTP_PORT=80": f"HTTP_PORT={sys.argv[6]}",
    "__HOST_GID__": sys.argv[7],
    "APP_IMAGE=__APP_IMAGE__": f"APP_IMAGE={sys.argv[8]}",
    "LLAMA_API_KEY=__GENERATE__": f"LLAMA_API_KEY={sys.argv[9]}",
    "EMBEDDING_API_KEY=__GENERATE__": f"EMBEDDING_API_KEY={sys.argv[10]}",
    "POSTGRES_PASSWORD=__GENERATE__": f"POSTGRES_PASSWORD={sys.argv[11]}",
    "__ACCELERATOR__": sys.argv[12],
    "__LLAMA_CPU_IMAGE__": sys.argv[13],
    "__LLAMA_GPU_IMAGE__": sys.argv[14],
    "__LLAMA_GPU_LAYERS__": sys.argv[15],
    "__LLAMA_GPU_LAYERS_DRAFT__": sys.argv[16],
    "__EMBEDDING_GPU_LAYERS__": sys.argv[17],
}
for old, new in replacements.items():
    template = template.replace(old, new)
Path(sys.argv[2]).write_text(template, encoding="utf-8")
PY
chmod 600 "$INSTALL_DIR/.env"
log "Generated private .env without printing secrets"

step "Generate API credentials for LAN clients"
printf '{"version": 1, "clients": []}\n' > "$INSTALL_DIR/config/auth/api_keys.json"
chmod 640 "$INSTALL_DIR/config/auth/api_keys.json"
for ((client_number = 1; client_number <= CLIENT_COUNT; client_number++)); do
  printf -v client_id 'client-%02d' "$client_number"
  "$INSTALL_DIR/scripts/offline/manage_client.sh" add "$client_id"
done
first_client_file="$INSTALL_DIR/config/clients/client-01.txt"
client_token="$(python3 - "$first_client_file" <<'PY'
import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.startswith("API key: "):
        print(line.removeprefix("API key: "))
        break
else:
    raise SystemExit("first client credential does not contain an API key")
PY
)"
log "Generated $CLIENT_COUNT unique client credential file(s)"

step "Start and validate database, vector, and model services"
export OFFLINE_ENV="$INSTALL_DIR/.env"
# shellcheck source=common.sh
source "$INSTALL_DIR/scripts/offline/common.sh"
compose config --quiet
if ! compose up -d --no-build --pull never \
  postgres chromadb llama-server embedding-server; then
  print_startup_diagnostics
  exit 1
fi
if ! wait_for_backend_services; then
  print_startup_diagnostics
  exit 1
fi

step "Index approved knowledge and configured figures"
log "First installation may spend several minutes describing each configured figure"
run_indexer 3

step "Configure persistent LAN firewall and Docker boot startup"
"$INSTALL_DIR/scripts/offline/configure_host.sh" \
  "$LAN_CIDR" "$SERVER_ADDRESS" "$HTTP_PORT" "$SSH_PORT" "$NETWORK_INTERFACE"

step "Start the chatbot API and Nginx gateway"
if ! compose up -d --no-build --pull never chatbot proxy; then
  print_startup_diagnostics
  exit 1
fi
if ! wait_for_service chatbot 60; then
  print_startup_diagnostics
  exit 1
fi
if ! wait_for_service proxy 30; then
  print_startup_diagnostics
  exit 1
fi

step "Run authenticated readiness and restart-policy checks"
curl --fail --silent --show-error \
  -H "Authorization: Bearer $client_token" \
  "$CHATBOT_ORIGIN/api/v1/ready"
echo
for service in postgres chromadb llama-server embedding-server chatbot proxy; do
  container_id="$(compose ps -q "$service")"
  restart_policy="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$container_id")"
  [[ "$restart_policy" == "unless-stopped" ]] || {
    echo "Unexpected restart policy for $service: $restart_policy" >&2
    exit 1
  }
  log "Reboot recovery enabled for $service"
done
systemctl is-enabled --quiet docker.service

step "Finalize installation and print operator outputs"
: > "$INSTALL_MARKER"
chmod 600 "$INSTALL_MARKER"
installation_complete=true
log "Installation complete: $INSTALL_DIR"
log "LAN API URL: $CHATBOT_ORIGIN"
log "Installation log: $INSTALL_LOG"
log "Docker and chatbot services will return automatically after a normal reboot"
echo
echo "==================================================================="
echo " Chatbot is ready on the LAN"
echo "==================================================================="
echo "Server address for other computers: $CHATBOT_ORIGIN"
echo "Client credential files (one file per client computer):"
for ((client_number = 1; client_number <= CLIENT_COUNT; client_number++)); do
  printf -v client_id 'client-%02d' "$client_number"
  echo "  $INSTALL_DIR/config/clients/$client_id.txt"
done
echo "Test from another computer:"
echo "  curl -H \"Authorization: Bearer <API key>\" $CHATBOT_ORIGIN/api/v1/ready"
echo "  (replace <API key> with the API key from the client's credential file)"
echo "==================================================================="
echo "Keep .env and api_keys.json private."
echo "Warning: HTTP traffic and API keys are not encrypted; use only on a trusted LAN."
