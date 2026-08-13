#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRAM="$ROOT_DIR/ProjectLeaf/leafos_taskpack/core/python/leaf_program.py"

if command -v python3 >/dev/null 2>&1; then
	exec python3 "$PROGRAM" "$@"
fi
if command -v python >/dev/null 2>&1; then
	exec python "$PROGRAM" "$@"
fi

printf '%s\n' 'program: LeafOS program needs Python 3 on PATH.' >&2
exit 127
