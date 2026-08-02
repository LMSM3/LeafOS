#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "index" || "${1:-}" == "query" || "${1:-}" == "pack" ||
      "${1:-}" == "stats" || "${1:-}" == "archive" || "${1:-}" == "checkpoint" ||
      ( "${1:-}" == "append" && " $* " == *" --kind "* ) ]]; then
    exec python3 "$ROOT_DIR/core/memory/memory_cli.py" "$@"
fi
if [[ -n "${LEAF_MEMORY_BIN:-}" ]]; then
    memory_bin="$LEAF_MEMORY_BIN"
elif [[ -x "$ROOT_DIR/build/leaf-memory" ]]; then
    memory_bin="$ROOT_DIR/build/leaf-memory"
elif [[ -x "$ROOT_DIR/build/leaf-memory.exe" ]]; then
    memory_bin="$ROOT_DIR/build/leaf-memory.exe"
else
    printf 'leaf-memory: native executable not found; run make first or set LEAF_MEMORY_BIN.\n' >&2
    exit 127
fi
exec "$memory_bin" "$@"
