#!/usr/bin/env bash
# Chatbot release installer entrypoint. The implementation lives in the
# step modules under scripts/setup/; this file validates arguments and
# orchestrates the numbered installation steps.
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/compose/docker-compose.offline.yml" ]]; then
  INSTALL_DIR="$SCRIPT_DIR"
else
  INSTALL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
SETUP_MODULES_DIR="$INSTALL_DIR/scripts/setup"
MODEL_DIR="$INSTALL_DIR/models"
IMAGES_DIR="$INSTALL_DIR/images"
BIND_ADDRESS="${BIND_ADDRESS:-0.0.0.0}"
SERVER_ADDRESS="${SERVER_ADDRESS:-}"
LAN_CIDR="${LAN_CIDR:-}"
HTTP_PORT="${HTTP_PORT:-80}"
SSH_PORT="${SSH_PORT:-22}"
CLIENT_COUNT="${CLIENT_COUNT:-5}"
GPU="yes"
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

for setup_module in common release rollback host deploy; do
  [[ -f "$SETUP_MODULES_DIR/$setup_module.sh" ]] || {
    echo "setup.sh step module is missing: $SETUP_MODULES_DIR/$setup_module.sh" >&2
    echo "Unzip the current chatbot.zip over $INSTALL_DIR before running setup.sh." >&2
    exit 1
  }
done

# shellcheck source=setup/common.sh
source "$SETUP_MODULES_DIR/common.sh"
# shellcheck source=setup/release.sh
source "$SETUP_MODULES_DIR/release.sh"
# shellcheck source=setup/rollback.sh
source "$SETUP_MODULES_DIR/rollback.sh"
# shellcheck source=setup/host.sh
source "$SETUP_MODULES_DIR/host.sh"
# shellcheck source=setup/deploy.sh
source "$SETUP_MODULES_DIR/deploy.sh"
trap report_error ERR
trap rollback_incomplete_installation EXIT

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
verify_release_archives

step "Verify the chatbot folder matches chatbot.zip"
verify_folder_matches_chatbot_zip

step "Replenish image archives and model files"
replenish_release_content

step "Detect the primary LAN address and subnet"
select_lan_network

step "Verify release files, model filenames, and free space"
verify_release_files_and_free_space

step "Load only missing or changed Docker images and verify required tags"
load_release_images

step "Preflight host firewall prerequisites"
preflight_host_firewall

step "Validate the selected bind address and HTTP port"
validate_bind_address
if [[ "$reset_incomplete_installation" == true ]]; then
  stopped_incomplete_gpu_containers=()
  cleanup_incomplete_installation
fi

step "Remove existing chatbot containers and volumes"
remove_existing_chatbot_resources

step "Remove legacy chatbot images from previous releases"
remove_legacy_images

step "Generate runtime configuration and service secrets"
generate_runtime_configuration

step "Generate API credentials for LAN clients"
generate_client_credentials

step "Start and validate database, vector, and model services"
start_backend_services

step "Index approved knowledge and configured figures"
index_approved_knowledge

step "Configure persistent LAN firewall and Docker boot startup"
configure_persistent_firewall

step "Start the chatbot API and Nginx gateway"
start_chatbot_and_proxy

step "Run authenticated readiness and restart-policy checks"
verify_service_readiness

step "Finalize installation and print operator outputs"
finalize_installation