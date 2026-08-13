#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "Python 3.9+ was not found." >&2
  exit 1
fi

"$PY" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else "Python 3.9+ is required.")
PY

echo "FlowerOS Hardware Monitor installer"
"$PY" -m venv .venv
VENV_PY="$ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  VENV_PY="$ROOT/.venv/Scripts/python.exe"
fi

"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -e .

if [[ "${1:-}" != "--no-smoke" ]]; then
  "$VENV_PY" -m unittest discover -s tests
  "$VENV_PY" -m floweros_hwmon --once --no-alt-screen
fi

echo
echo "Installed. Run with:"
echo "  ./run.sh"
echo "  .venv/bin/floweros-hwmon"
