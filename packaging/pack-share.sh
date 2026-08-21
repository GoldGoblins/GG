#!/usr/bin/env bash
# Build a share zip: GG AI Desktop + GROK TUI launcher. No GGUF models.

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'FAIL: do not source\n' >&2
  return 78
fi

set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$HERE/.." && pwd)"
STAMP="$(date -u +%Y%m%d)"
OUT_DIR="${1:-/home/GG/GoldGoblins/backups}"
STAGE="$(mktemp -d /tmp/gg-ai-desktop-share.XXXXXX)"
NAME="GG-AI-Desktop-GROK-TUI-${STAMP}"
ROOT="$STAGE/$NAME"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

mkdir -p "$ROOT/app" "$OUT_DIR"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.gg-ai-desktop-live' \
  "$PROJECT/" "$ROOT/app/"
cp "$HERE/share/run-gg-ai-desktop.sh" "$ROOT/run-gg-ai-desktop.sh"
cp "$HERE/share/update-gg-ai-desktop.sh" "$ROOT/update-gg-ai-desktop.sh"
cp "$HERE/share/README.txt" "$ROOT/README.txt"
chmod 0755 "$ROOT/run-gg-ai-desktop.sh" "$ROOT/update-gg-ai-desktop.sh"

ZIP="$OUT_DIR/${NAME}.zip"
rm -f "$ZIP"
(cd "$STAGE" && zip -rq "$ZIP" "$NAME")
sha256sum "$ZIP" | awk '{print $1}' > "${ZIP}.sha256"
printf 'SHARE_ZIP=%s\n' "$ZIP"
printf 'SHA256=%s\n' "$(cat "${ZIP}.sha256")"
printf 'BYTES=%s\n' "$(wc -c < "$ZIP")"
