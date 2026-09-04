# Release ZIP content: verification, image archives, model files, and image loading.

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
      log "images/$archive_name already matches this release; using the existing file"
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

verify_release_archives() {
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
}

verify_folder_matches_chatbot_zip() {
  unzip -p "$CHATBOT_ZIP" chatbot/SHA256SUMS > "$INSTALL_DIR/SHA256SUMS"
  unzip -p "$CHATBOT_ZIP" chatbot/release-manifest.json > "$INSTALL_DIR/release-manifest.json"
  log "Refreshed SHA256SUMS and release-manifest.json from chatbot.zip"
  verify_source_matches_chatbot_zip
}

replenish_release_content() {
  mkdir -p "$IMAGES_DIR"
  replenish_image_archives
  prune_stale_archives
  replenish_models
}

verify_release_files_and_free_space() {
  verify_models
  (
    cd "$INSTALL_DIR"
    sha256sum -c SHA256SUMS --ignore-missing
  )
  local available_kb required_kb
  available_kb="$(df -Pk "$INSTALL_DIR" | awk 'NR==2 {print $4}')"
  required_kb=$((20 * 1024 * 1024))
  if (( available_kb < required_kb )); then
    echo "At least 20 GB free space is required in $INSTALL_DIR." >&2
    exit 1
  fi
  log "Release checksums passed; at least 20 GB free space is available"
}

load_release_images() {
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
}