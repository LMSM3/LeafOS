#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$(command -v python3 || command -v python)"
export PYTHONDONTWRITEBYTECODE=1

"$python_bin" "$ROOT_DIR/tests/test_agent_loop.py"

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

"$ROOT_DIR/bin/leafctl" agent-loop-start \
  --target "$tmp_root/Games" \
  --projects generic-python-sim \
  --profile cpu-only \
  --run-dir "$tmp_root/run" \
  --yes >/dev/null

"$ROOT_DIR/bin/leafctl" agent-loop-status "$tmp_root/run" --json | grep -q '"leafos_object": "agent_loop_status"'
"$ROOT_DIR/bin/leafctl" agent-loop-tick "$tmp_root/run" >/dev/null
"$ROOT_DIR/bin/leafctl" agent-loop-report "$tmp_root/run" | grep -q 'LeafOS Agent Loop Report'

echo "agent loop tests passed"
