#!/usr/bin/env bash
# WO-004-C-02 -- completion_worm.sh
# Thin wrapper around completion_worm.py (the completion worm pass).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"
command -v "$PY" >/dev/null 2>&1 || { echo "completion_worm.sh: python not found" >&2; exit 1; }
exec "$PY" "$HERE/completion_worm.py" "$@"
