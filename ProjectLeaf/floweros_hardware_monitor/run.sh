#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$ROOT/.venv/Scripts/python.exe"
fi

if [[ ! -x "$VENV_PY" ]]; then
  "$ROOT/install.sh" --no-smoke
fi

exec "$VENV_PY" -m floweros_hwmon "$@"
