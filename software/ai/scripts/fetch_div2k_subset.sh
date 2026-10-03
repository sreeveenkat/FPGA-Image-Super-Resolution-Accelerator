#!/usr/bin/env bash
# Download a subset of DIV2K *training* images (img0193..img0384) from the Hugging Face mirror
# ScooterTaylor/DIV2K_captioned_subset into data/train/HR/. Resumable; safe to re-run.
# Usage: software/ai/scripts/fetch_div2k_subset.sh [COUNT]   (default 60)
set -u
COUNT=${1:-60}
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DEST="$ROOT/data/train/HR"
mkdir -p "$DEST"
BASE="https://huggingface.co/datasets/ScooterTaylor/DIV2K_captioned_subset/resolve/main"
for i in $(seq 193 $((192 + COUNT))); do
  f=$(printf "img%04d.png" "$i")
  [ -f "$DEST/$f" ] && continue
  for try in 1 2 3 4 5; do
    # -f: fail on HTTP errors (otherwise an error page would be saved as a .png); then require the PNG signature
    curl -sLf --max-time 600 -C - -o "$DEST/$f.part" "$BASE/$f" && [ "$(head -c 4 "$DEST/$f.part" | tail -c 3)" = "PNG" ] && mv "$DEST/$f.part" "$DEST/$f" && break
    rm -f "$DEST/$f.part"
    sleep 3
  done
  echo "$(date +%T) $f $(ls "$DEST"/*.png 2>/dev/null | wc -l)"
done
echo DONE
