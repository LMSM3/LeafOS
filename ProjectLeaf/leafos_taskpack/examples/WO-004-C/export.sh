#!/usr/bin/env bash
# WO-004-C-02 -- export.sh
# Export gate wrapper: packages the verified wakeup module into exports/.
# Delegates to export.py so packaging is portable (no external zip needed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"
command -v "$PY" >/dev/null 2>&1 || { echo "export.sh: python not found" >&2; exit 1; }
WORK_ORDER="${1:-WO-004-C}"
exec "$PY" "$HERE/export.py" "$WORK_ORDER"
