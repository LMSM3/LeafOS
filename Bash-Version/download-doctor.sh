#!/usr/bin/env bash
# LeafOS download doctor: hash and inventory already-downloaded model artifacts.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$HERE/.." && pwd)"
INSTALLER="$ROOT_DIR/ProjectLeaf/leaf_model_installer"

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  if [[ -x "$INSTALLER/.venv/bin/python" ]]; then
    printf '%s\n' "$INSTALLER/.venv/bin/python"
    return
  fi
  if [[ -x "$INSTALLER/.venv/bin/python3" ]]; then
    printf '%s\n' "$INSTALLER/.venv/bin/python3"
    return
  fi
  if [[ -x "$INSTALLER/.venv/Scripts/python.exe" ]]; then
    printf '%s\n' "$INSTALLER/.venv/Scripts/python.exe"
    return
  fi
  printf 'python/python3 not found; download doctor requires Python.\n' >&2
  exit 2
}

PYTHON_BIN="$(pick_python)"

if [[ ! -f "$INSTALLER/leaf_models/install_cli.py" ]]; then
  printf 'leaf model installer not found: %s\n' "$INSTALLER" >&2
  exit 2
fi

PYTHONPATH="$INSTALLER${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -B -m leaf_models.install_cli download-doctor "$@"
