#!/usr/bin/env bash
# LeafOS Bash entrypoint.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASKPACK="$ROOT_DIR/ProjectLeaf/leafos_taskpack"
LEAFCTL="$TASKPACK/bin/leafctl"
CHAT_LOCAL="$ROOT_DIR/Bash-Version/chat-local.sh"
DOWNLOAD_DOCTOR="$ROOT_DIR/Bash-Version/download-doctor.sh"

case "${1:-}" in
  chat-local|local-chat|chat-real)
    shift
    exec bash "$CHAT_LOCAL" "$@"
    ;;
  download)
    if [[ "${2:-}" == "doctor" ]]; then
      shift 2
      exec bash "$DOWNLOAD_DOCTOR" "$@"
    fi
    ;;
esac

if [[ ! -f "$LEAFCTL" ]]; then
  printf 'LeafOS source command not found: %s\n' "$LEAFCTL" >&2
  exit 1
fi

exec bash "$LEAFCTL" "$@"
