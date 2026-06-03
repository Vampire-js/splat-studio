#!/usr/bin/env bash
# Download the brush 3DGS trainer binary into worker/bin/brush.
# brush is a Rust/wgpu app — runs on Vulkan, no CUDA toolkit required.
set -euo pipefail

VERSION="${BRUSH_VERSION:-v0.3.0}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$HERE/bin"
mkdir -p "$BIN_DIR"

uname_s="$(uname -s)"
uname_m="$(uname -m)"

case "$uname_s/$uname_m" in
  Linux/x86_64)   asset="brush-app-x86_64-unknown-linux-gnu.tar.xz" ;;
  Darwin/arm64)   asset="brush-app-aarch64-apple-darwin.tar.xz" ;;
  Darwin/x86_64)  echo "No prebuilt brush for Intel macOS; build from source: https://github.com/ArthurBrussee/brush" >&2; exit 1 ;;
  *)              echo "Unsupported platform $uname_s/$uname_m. See https://github.com/ArthurBrussee/brush/releases" >&2; exit 1 ;;
esac

url="https://github.com/ArthurBrussee/brush/releases/download/${VERSION}/${asset}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "Downloading $asset ..."
curl -fL --progress-bar -o "$tmp/brush.tar.xz" "$url"

echo "Extracting ..."
tar -xJf "$tmp/brush.tar.xz" -C "$tmp"

# The archive has a single top-level dir with brush_app inside.
src_bin="$(find "$tmp" -type f -name 'brush_app' | head -1)"
if [ -z "$src_bin" ]; then
  echo "Could not find brush_app in archive." >&2
  exit 1
fi

mv "$src_bin" "$BIN_DIR/brush"
chmod +x "$BIN_DIR/brush"
echo "Installed: $BIN_DIR/brush"
"$BIN_DIR/brush" --version
