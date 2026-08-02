#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_DIR="$ROOT_DIR/core/python"

# Respect the same Python discovery that leafctl uses.
LEAFCTL_PYTHON="${LEAFCTL_PYTHON:-}"
if [[ -z "${LEAFCTL_PYTHON}" ]]; then
	for candidate in "$(command -v python3 2>/dev/null || true)" \
					 "$(command -v python 2>/dev/null || true)" \
					 /c/msys64/ucrt64/bin/python.exe \
					 /c/Python313/python.exe \
					 "$USERPROFILE/AppData/Local/Programs/Python/Python313/python.exe"; do
		if [[ -n "$candidate" && -x "$candidate" ]]; then
			LEAFCTL_PYTHON="$candidate"
			break
		fi
	done
fi

[[ -n "${LEAFCTL_PYTHON}" ]] || {
	echo "ERROR: Python not found; set LEAFCTL_PYTHON" >&2
	exit 1
}

export PYTHONPATH="${PYTHON_DIR}${PYTHONPATH:+:$PYTHONPATH}"
exec "$LEAFCTL_PYTHON" "$ROOT_DIR/tests/test_authority_boundary.py"
