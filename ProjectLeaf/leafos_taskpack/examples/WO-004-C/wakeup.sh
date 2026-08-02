#!/usr/bin/env bash
# WO-004-C -- wakeup.sh
# Bash wrapper and run-folder creator for the LeafOS wakeup runtime node.
# Branch logic, payloads, and logging live in wakeup.py; this wrapper only
# resolves a python interpreter, ensures runs/ exists, and passes args through.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [[ -z "$PY" ]]; then
    echo "wakeup.sh: python3 not found" >&2
    exit 1
fi

# wakeup.py writes the timestamped run folder; make sure the root exists first.
mkdir -p "$HERE/runs"

exec "$PY" "$HERE/wakeup.py" "$@"