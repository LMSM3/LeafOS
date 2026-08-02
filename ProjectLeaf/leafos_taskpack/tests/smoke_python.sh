#!/usr/bin/env bash
# tests/smoke_python.sh -- Python layer smoke tests
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEAFPY="$ROOT_DIR/bin/leafpy"

if ! command -v python3 &>/dev/null; then
    echo "SKIP: python3 not found" >&2; exit 0
fi
[[ -f "$LEAFPY" ]] || { echo "ERROR: $LEAFPY not found" >&2; exit 1; }
chmod +x "$LEAFPY"

echo "[leafpy] doctor"
python3 "$LEAFPY" doctor

echo "[leafpy] status"
python3 "$LEAFPY" status | grep -q "LeafOS"

echo "[leafpy] platform"
python3 "$LEAFPY" platform | grep -q "os="

echo "[leafpy] loaders"
python3 "$LEAFPY" loaders | grep -q "orbit"

echo "[leafpy] versions"
python3 "$LEAFPY" versions | grep -q "python"

echo "smoke_python.sh: all checks passed"
