#!/usr/bin/env bash
set -euo pipefail

if [[ -d /ucrt64/bin ]]; then
  export PATH="/ucrt64/bin:/usr/bin:$PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CC_BIN="${CC:-gcc}"
OUT_DIR="$ROOT_DIR/build"
EXT=""
case "$(uname -s 2>/dev/null || true)" in
  MINGW*|MSYS*|CYGWIN*) EXT=".exe" ;;
esac
OUT="$OUT_DIR/leaf-tui$EXT"
SOCKET_LIBS=()
if [[ -n "$EXT" ]]; then
  SOCKET_LIBS=(-lws2_32)
fi
mkdir -p "$OUT_DIR"

"$CC_BIN" \
  -std=c11 -O2 -Wall -Wextra -Wpedantic \
  -I"$ROOT_DIR/core/tui" \
  "$ROOT_DIR/core/tui/leaf_tui.c" \
  "$ROOT_DIR/core/tui/leaf_tui_json.c" \
  "$ROOT_DIR/core/tui/leaf_tui_state.c" \
  "$ROOT_DIR/core/tui/leaf_tui_pages.c" \
  "$ROOT_DIR/core/tui/leaf_tui_input.c" \
  -o "$OUT" -lncursesw "${SOCKET_LIBS[@]}"

printf 'built %s\n' "$OUT"
