#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-0.2.3}"
CHATBOT_OUTPUT="${2:-$(dirname "$ROOT")/chatbot_bca.zip}"
IMAGES_OUTPUT="${3:-$(dirname "$ROOT")/images.zip}"
[[ "$CHATBOT_OUTPUT" = /* ]] || CHATBOT_OUTPUT="$ROOT/$CHATBOT_OUTPUT"
[[ "$IMAGES_OUTPUT" = /* ]] || IMAGES_OUTPUT="$ROOT/$IMAGES_OUTPUT"
APP_IMAGE="chatbot-bca:$VERSION"
LLAMA_CPU_SOURCE="ghcr.io/ggml-org/llama.cpp:server@sha256:991cf50e9eb7dee4c18090849c7f909bafc5a1884cdde2dc3011df7407da09d6"
LLAMA_GPU_SOURCE="ghcr.io/ggml-org/llama.cpp:server-cuda@sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce"
POSTGRES_SOURCE="postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777"
CHROMA_SOURCE="chromadb/chroma:latest@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6"
NGINX_SOURCE="nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
LLAMA_CPU_IMAGE="chatbot-bca/llama.cpp-server-cpu:991cf50e9eb"
LLAMA_GPU_IMAGE="chatbot-bca/llama.cpp-server-cuda:b2497f8834f5"
POSTGRES_IMAGE="chatbot-bca/postgres:57c72fd2a128"
CHROMA_IMAGE="chatbot-bca/chromadb:1e0b73a187a2"
NGINX_IMAGE="chatbot-bca/nginx:65645c7bb6a0"

for command in awk docker git tar sha256sum zip unzip python3; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing command: $command" >&2
    exit 1
  }
done
[[ "$(uname -m)" == "x86_64" ]] || {
  echo "Offline ZIPs must be prepared on an x86_64 computer." >&2
  exit 1
}
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][a-zA-Z0-9.-]+)?$ ]] || {
  echo "Version must look like 0.2.3" >&2
  exit 1
}
PROJECT_VERSION="$(awk '
  /^\[project\]$/ { in_project = 1; next }
  in_project && /^version = "/ { gsub(/^version = "|"$/, ""); print; exit }
' "$ROOT/pyproject.toml")"
[[ "$VERSION" == "$PROJECT_VERSION" ]] || {
  echo "Release version $VERSION does not match project version $PROJECT_VERSION." >&2
  exit 1
}
[[ "$CHATBOT_OUTPUT" != "$IMAGES_OUTPUT" ]] || {
  echo "CHATBOT_OUTPUT and IMAGES_OUTPUT must be different files." >&2
  exit 1
}
git -C "$ROOT" rev-parse --verify HEAD >/dev/null
if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "Refusing to prepare a release from a dirty Git working tree." >&2
  echo "Commit the intended source so chatbot_bca.zip can contain exactly Git HEAD." >&2
  exit 1
fi
for output in "$CHATBOT_OUTPUT" "$IMAGES_OUTPUT"; do
  [[ ! -e "$output" ]] || {
    echo "Output already exists: $output" >&2
    echo "Remove both release ZIPs before rebuilding." >&2
    exit 1
  }
done

stage_parent="$(mktemp -d)"
stage="$stage_parent/chatbotbca"
chatbot_tmp="$(dirname "$CHATBOT_OUTPUT")/.chatbot_bca.$$.zip"
images_tmp="$(dirname "$IMAGES_OUTPUT")/.images.$$.zip"
chatbot_published=false
release_published=false
cleanup() {
  rm -rf "$stage_parent"
  rm -f "$chatbot_tmp" "$images_tmp"
  if [[ "$chatbot_published" == true && "$release_published" != true ]]; then
    rm -f "$CHATBOT_OUTPUT"
  fi
}
trap cleanup EXIT
mkdir -p "$stage/images" "$(dirname "$CHATBOT_OUTPUT")" "$(dirname "$IMAGES_OUTPUT")"

source_commit="$(git -C "$ROOT" rev-parse HEAD)"
git -C "$ROOT" archive --format=tar "$source_commit" | tar -C "$stage" -xf -
[[ -f "$stage/scripts/install.sh" ]] || {
  echo "Committed source is missing scripts/install.sh." >&2
  exit 1
}
cp "$stage/scripts/install.sh" "$stage/install.sh"
chmod 755 "$stage/install.sh" "$stage/scripts/accelerator.sh" \
  "$stage/scripts/prepare.sh" "$stage/scripts/install.sh" \
  "$stage/scripts/offline"/*.sh

for image in "$LLAMA_CPU_SOURCE" "$LLAMA_GPU_SOURCE" "$POSTGRES_SOURCE" \
  "$CHROMA_SOURCE" "$NGINX_SOURCE"; do
  docker pull "$image"
done
docker tag "$LLAMA_CPU_SOURCE" "$LLAMA_CPU_IMAGE"
docker tag "$LLAMA_GPU_SOURCE" "$LLAMA_GPU_IMAGE"
docker tag "$POSTGRES_SOURCE" "$POSTGRES_IMAGE"
docker tag "$CHROMA_SOURCE" "$CHROMA_IMAGE"
docker tag "$NGINX_SOURCE" "$NGINX_IMAGE"
DOCKER_BUILDKIT=1 docker build --pull=false -t "$APP_IMAGE" "$stage"
docker save -o "$stage/images/runtime-images.tar" \
  "$APP_IMAGE" "$LLAMA_CPU_IMAGE" "$LLAMA_GPU_IMAGE" "$POSTGRES_IMAGE" \
  "$CHROMA_IMAGE" "$NGINX_IMAGE"

python3 - "$stage/release-manifest.json" "$VERSION" "$source_commit" "$APP_IMAGE" \
  "$LLAMA_CPU_IMAGE" "$LLAMA_GPU_IMAGE" "$POSTGRES_IMAGE" "$CHROMA_IMAGE" \
  "$NGINX_IMAGE" "$LLAMA_CPU_SOURCE" "$LLAMA_GPU_SOURCE" "$POSTGRES_SOURCE" \
  "$CHROMA_SOURCE" "$NGINX_SOURCE" <<'PY'
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
images = sys.argv[4:10]
source_images = sys.argv[10:15]
manifest = {
    "format_version": 6,
    "release": sys.argv[2],
    "source_commit": sys.argv[3],
    "architecture": "x86_64",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "builder_architecture": platform.machine(),
    "app_image": sys.argv[4],
    "accelerator_images": {"cpu": sys.argv[5], "gpu": sys.argv[6]},
    "images": images,
    "image_sources": dict(zip(images[1:], source_images, strict=True)),
}
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

(
  cd "$stage"
  find . -type f ! -name SHA256SUMS ! -path './images/runtime-images.tar' \
    -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
  sha256sum -c SHA256SUMS
)

(
  cd "$stage_parent"
  zip -q -0 -r "$chatbot_tmp" chatbotbca -x 'chatbotbca/images/*'
  zip -q -0 -r "$images_tmp" chatbotbca/images
)
unzip -tq "$chatbot_tmp"
unzip -tq "$images_tmp"
mv "$chatbot_tmp" "$CHATBOT_OUTPUT"
chatbot_published=true
if ! mv "$images_tmp" "$IMAGES_OUTPUT"; then
  rm -f "$CHATBOT_OUTPUT"
  echo "Failed to publish both release ZIPs; removed partial output." >&2
  exit 1
fi
release_published=true

echo "Created source: $CHATBOT_OUTPUT"
echo "Created Docker images: $IMAGES_OUTPUT"
echo "Source commit: $source_commit"
echo "GGUF models are not included. Extract both ZIPs, then place models in chatbotbca/models/."
