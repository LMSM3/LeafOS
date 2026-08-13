#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$ROOT_DIR/ProjectLeaf/leafos_taskpack/system/serve_leaf.py"

if [[ ! -f "$SERVER" ]]; then
  printf 'serve_leaf.py not found: %s\n' "$SERVER" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SERVER" "$@"
elif command -v python >/dev/null 2>&1; then
  exec python "$SERVER" "$@"
else
  printf 'Python 3 was not found.\n' >&2
  exit 1
fi
