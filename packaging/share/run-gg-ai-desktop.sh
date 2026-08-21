#!/usr/bin/env bash
# Share launcher for GG AI Desktop. GROK TUI is the intended motor.
# No sudo. Does not start gg-host. Does not require local GGUF models.

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'FAIL: do not source this file. Run: bash %s\n' "${BASH_SOURCE[0]}" >&2
  return 78
fi

set -Eeuo pipefail
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONDONTWRITEBYTECODE=1

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

HERE="$(cd "$(dirname "$0")" && pwd)"
if [[ "${1:-}" == "--update" ]]; then
  shift
  UPDATE="$HERE/update-gg-ai-desktop.sh"
  if [[ ! -x "$UPDATE" ]]; then
    fail "update-gg-ai-desktop.sh missing"
  fi
  "$UPDATE"
fi
PROJECT="$HERE/app"
if [[ ! -f "$PROJECT/main.py" && -f "$HERE/main.py" ]]; then
  PROJECT="$HERE"
fi
if [[ ! -f "$PROJECT/main.py" && -f "$HERE/../main.py" ]]; then
  PROJECT="$(cd "$HERE/.." && pwd)"
fi
if [[ ! -f "$PROJECT/main.py" && -f "$HERE/../../main.py" ]]; then
  PROJECT="$(cd "$HERE/../.." && pwd)"
fi
if [[ ! -f "$PROJECT/main.py" && -f /home/GG/GoldGoblins/projects/gg-ai-desktop/main.py ]]; then
  PROJECT=/home/GG/GoldGoblins/projects/gg-ai-desktop
fi
MAIN="$PROJECT/main.py"
PYTHON="${PYTHON:-/usr/bin/python3}"

if [[ ! -x "$PYTHON" ]]; then
  fail "python3 missing"
fi
if [[ ! -f "$MAIN" ]]; then
  fail "app/main.py missing — unpack the zip first"
fi

if ! "$PYTHON" - <<'PY'
import sys
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
except Exception:
    sys.exit(2)
sys.exit(0)
PY
then
  fail "PySide6/Qt missing. Fedora: dnf install python3-pyside6 qt6-qtwebengine"
fi

find_grok() {
  if [[ -n "${GG_GROK_BIN:-}" && -x "${GG_GROK_BIN}" ]]; then
    printf '%s\n' "$GG_GROK_BIN"
    return 0
  fi
  if command -v grok >/dev/null 2>&1; then
    command -v grok
    return 0
  fi
  local candidate
  for candidate in \
    "$HOME/.local/bin/grok" \
    "$HOME/.local/share/goldgoblins/tools/grok-build/1.0.5/grok"
  do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

if ! GROK_BIN="$(find_grok)"; then
  fail "grok CLI missing. Install Grok Build from xAI, then: grok login"
fi

STATE="${XDG_STATE_HOME:-$HOME/.local/state}/gg-ai-desktop-share"
mkdir -p "$STATE/grok-home"
export GG_GROK_BIN="$GROK_BIN"
export GG_GROK_HOME="${GG_GROK_HOME:-$STATE/grok-home}"
export GG_WORKSPACE="${GG_WORKSPACE:-$PWD}"
export GG_GROK_PRODUCT_HOME="${GG_GROK_PRODUCT_HOME:-$STATE/product-grok-home}"

if [[ -z "${WAYLAND_DISPLAY:-}" && -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/wayland-0" ]]; then
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export WAYLAND_DISPLAY=wayland-0
fi
if [[ -z "${DISPLAY:-}" && -S /tmp/.X11-unix/X0 ]]; then
  export DISPLAY=:0
fi
if [[ -z "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
  fail "no display (Wayland or X11)"
fi

printf 'GG_AI_DESKTOP=SHARE\n'
printf 'MOTOR=GROK_TUI\n'
printf 'GG_GROK_BIN=%s\n' "$GG_GROK_BIN"
printf 'GG_WORKSPACE=%s\n' "$GG_WORKSPACE"
cd "$PROJECT"
exec "$PYTHON" -B "$MAIN"
