#!/usr/bin/env bash
# WO-004-C-02 -- tests/test_wakeup_shell.sh
# Bash and CLI smoke checks for the wakeup node.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE="$(cd "$HERE/.." && pwd)"
cd "$MODULE"

PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"
command -v "$PY" >/dev/null 2>&1 || { echo "SKIP: python not found" >&2; exit 0; }

pass() { echo "  [ok] $*"; }
fail() { echo "  [XX] $*" >&2; exit 1; }

echo "[wakeup] bash -n"
bash -n wakeup.sh || fail "bash -n wakeup.sh"
pass "bash -n wakeup.sh"

echo "[wakeup] py_compile"
"$PY" -m py_compile wakeup.py || fail "py_compile wakeup.py"
pass "py_compile wakeup.py"

chmod +x wakeup.sh 2>/dev/null || true

echo "[wakeup] --force tails"
out_tails="$(./wakeup.sh --force tails)"
echo "$out_tails" | grep -Eq "Good (morning|afternoon), the time is" || fail "tails greeting missing"
pass "tails greeting present"
test -f runs/latest/wakeup_result.json || fail "tails result json missing"
"$PY" tests/test_wakeup_json.py runs/latest/wakeup_result.json || fail "tails json structure"
pass "tails json structure"

echo "[wakeup] --force heads --ticker NVDA"
out_heads="$(./wakeup.sh --force heads --ticker NVDA)"
echo "$out_heads" | grep -q "Welcome back from the after life" || fail "heads prompt missing"
echo "$out_heads" | grep -q "wakeup_stock_payload" || fail "heads payload missing"
pass "heads prompt + payload present"
test -f runs/latest/wakeup_result.json || fail "heads result json missing"
"$PY" tests/test_wakeup_json.py runs/latest/wakeup_result.json || fail "heads json structure"
pass "heads json structure"

echo "[wakeup] csv log"
test -f runs/wakeup_log.csv || fail "csv log missing"
head -n1 runs/wakeup_log.csv | grep -q "local_datetime,branch,message" || fail "csv header malformed"
pass "csv log present"

echo "test_wakeup_shell.sh: all checks passed"
