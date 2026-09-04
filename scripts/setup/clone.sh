# Source/deployment boundary for the offline installer.

populate_source_resource_cache() {
  local resource_dir resource_zip resource_label
  for resource_label in images models; do
    if [[ "$resource_label" == "images" ]]; then
      resource_dir="$INSTALL_DIR/images"
      resource_zip="$IMAGES_ZIP"
    else
      resource_dir="$INSTALL_DIR/models"
      resource_zip="$MODELS_ZIP"
    fi
    [[ -d "$resource_dir" ]] && continue
    [[ -f "$resource_zip" ]] || {
      echo "Source $resource_label cache is absent and $resource_zip is not available." >&2
      echo "Copy the required ZIP beside chatbot.zip before running setup.sh." >&2
      exit 1
    }
    command -v unzip >/dev/null 2>&1 || {
      echo "Missing prerequisite for source resource cache: unzip" >&2
      exit 1
    }
    echo "Source $resource_label cache is absent; extracting $resource_zip" >&2
    unzip -q "$resource_zip" -d "$(dirname "$INSTALL_DIR")"
  done
}

prepare_deployed_clone() {
  local deployment_dir entry_path entry_relative

  [[ "${CHATBOT_DEPLOYMENT:-}" == "1" ]] && return 0
  deployment_dir="$(dirname "$INSTALL_DIR")/chatbot_offline"
  [[ "$INSTALL_DIR" == "$deployment_dir" ]] && return 0

  if [[ "$MODE" == "offline" ]]; then
    [[ -f "$CHATBOT_ZIP" ]] || {
      echo "Required release archive not found: $CHATBOT_ZIP" >&2
      echo "Copy chatbot.zip into $ZIP_DIR or pass --zip-dir / ZIP_DIR." >&2
      exit 1
    }
    populate_source_resource_cache
  fi
  command -v tar >/dev/null 2>&1 || {
    echo "Missing prerequisite for deployment clone: tar" >&2
    exit 1
  }
  echo "Replacing deployed clone: $deployment_dir" >&2
  rm -rf "$deployment_dir"
  mkdir -p "$deployment_dir"
  (
    cd "$INSTALL_DIR"
    tar \
      --exclude='./.env' \
      --exclude='./.git' \
      --exclude='./.git/*' \
      --exclude='./.venv' \
      --exclude='./.venv/*' \
      --exclude='./backups' \
      --exclude='./backups/*' \
      --exclude='./config/.installed' \
      --exclude='./config/auth' \
      --exclude='./config/auth/*' \
      --exclude='./config/clients' \
      --exclude='./config/clients/*' \
      --exclude='./config/tls' \
      --exclude='./config/tls/*' \
      --exclude='./install.log' \
      --exclude='./runtime' \
      --exclude='./runtime/*' \
      -cf - .
  ) | tar -C "$deployment_dir" -xf -

  entry_path="$SCRIPT_DIR/$(basename "$0")"
  entry_relative="${entry_path#"$INSTALL_DIR"/}"
  [[ -f "$deployment_dir/$entry_relative" ]] || {
    echo "Deployment entrypoint is missing: $deployment_dir/$entry_relative" >&2
    exit 1
  }
  exec env CHATBOT_DEPLOYMENT=1 CHATBOT_SOURCE_DIR="$INSTALL_DIR" \
    "$deployment_dir/$entry_relative" "$@"
}
