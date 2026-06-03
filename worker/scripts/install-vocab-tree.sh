#!/usr/bin/env bash
# Download a pretrained COLMAP vocabulary tree for `vocab_tree` matching.
#
# Three options exist (32K / 256K / 1M words). 32K is the right pick for
# typical photo-collection sizes (<= ~1000 images) and is ~36 MB.
#
# Hosted by the COLMAP team via demuc.de (same files COLMAP's docs link to).

set -euo pipefail

cd "$(dirname "$0")/.."   # -> worker/
mkdir -p models
cd models

FILE="vocab_tree_flickr100K_words32K.bin"
URL="https://demuc.de/colmap/${FILE}"

if [[ -f "$FILE" ]]; then
  echo "vocab tree already present: $(pwd)/$FILE"
  exit 0
fi

echo "Downloading $URL ..."
if command -v curl >/dev/null 2>&1; then
  curl -fL --retry 3 -o "$FILE" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$FILE" "$URL"
else
  echo "need curl or wget" >&2
  exit 1
fi

echo "saved to $(pwd)/$FILE ($(du -h "$FILE" | cut -f1))"
echo
echo "To use it, set in worker/.env:"
echo "  PIPELINE_MATCHER=vocab_tree   # or leave 'auto' to use it when N>80"
echo "  PIPELINE_VOCAB_TREE_PATH=./models/$FILE"
