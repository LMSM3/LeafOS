#!/usr/bin/env bash
# tests/nodes.sh -- Leaf SSH node system end-to-end smoke test (local transport)
# Exercises: node init, nodes add/list/ping, task submit -> done, jsonl log, task pull.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export LEAF_ROOT="$ROOT_DIR"
source "$ROOT_DIR/core/brand/brand.sh"

PASS=0
FAIL=0

PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [[ -z "$PY" ]]; then
    echo "SKIP: python3 not found (node engine requires Python 3.8+)" >&2
    exit 0
fi

TMP_ROOT="$(mktemp -d)"
trap "rm -rf $TMP_ROOT" EXIT
MASTER_HOME="$TMP_ROOT/master"
WORKER_HOME="$TMP_ROOT/worker"
PULL_DEST="$TMP_ROOT/pulled"
mkdir -p "$MASTER_HOME" "$WORKER_HOME" "$PULL_DEST"

_ok()   { PASS=$(( PASS + 1 )); printf "  %s[ok]%s   %s\n" "$C_GREEN_B" "$C_RESET" "$1"; }
_fail() { FAIL=$(( FAIL + 1 )); printf "  %s[FAIL]%s %s\n" "$C_RED_B" "$C_RESET" "$1" >&2; }

leaf() { LEAF_HOME="$MASTER_HOME" QUIET=1 bash "$ROOT_DIR/bin/leafctl" "$@"; }
worker_engine() { LEAF_HOME="$WORKER_HOME" "$PY" "$ROOT_DIR/core/node/leaf_node.py" "$@"; }

brand_banner
brand_header "tests/nodes.sh -- leaf ssh node system (local transport)"
printf "\n"

brand_step 1 "node init (worker)"
worker_engine init --node-id test-worker --json >/dev/null
if [[ -f "$WORKER_HOME/node.json" ]]; then _ok "worker node.json created"; else _fail "worker node.json missing"; fi

brand_step 2 "nodes add (local transport)"
leaf nodes add worker "$WORKER_HOME" --transport local --path "$WORKER_HOME" >/dev/null
if [[ -f "$MASTER_HOME/nodes.json" ]]; then _ok "master nodes.json created"; else _fail "master nodes.json missing"; fi

brand_step 3 "nodes list"
if leaf nodes list --json | grep -q worker; then _ok "worker present in registry"; else _fail "worker not listed"; fi

brand_step 4 "nodes ping"
if leaf nodes ping worker 2>/dev/null | grep -q ready; then _ok "worker ping state ready"; else _fail "ping not ready"; fi

brand_step 5 "task submit (echo)"
TASK_ID="$(leaf task submit worker "$ROOT_DIR/examples/echo.task.json" | tail -n1)"
if [[ -n "$TASK_ID" ]]; then _ok "task submitted: $TASK_ID"; else _fail "no task id returned"; fi

brand_step 6 "task reached done/"
if [[ -f "$WORKER_HOME/done/$TASK_ID.json" ]]; then _ok "task in done/"; else _fail "task not in done/"; fi

brand_step 7 "jsonl log stream"
LOG="$WORKER_HOME/logs/$TASK_ID.jsonl"
if [[ -f "$LOG" ]]; then
    if head -n1 "$LOG" | grep -q queued; then _ok "first event queued"; else _fail "first event not queued"; fi
    if tail -n1 "$LOG" | grep -q done; then _ok "last event done"; else _fail "last event not done"; fi
else
    _fail "log file missing"
fi

brand_step 8 "task pull (results)"
leaf task pull worker "$TASK_ID" "$PULL_DEST" >/dev/null
PULLED="$PULL_DEST/$TASK_ID/result.json"
if [[ -f "$PULLED" ]]; then
    _ok "result.json pulled"
    if grep -q "hello from the master" "$PULLED"; then _ok "result message present"; else _fail "result message missing"; fi
    if grep -q "\"status\": \"ok\"" "$PULLED"; then _ok "result status ok"; else _fail "status not ok"; fi
else
    _fail "result.json not pulled"
fi

printf "\n"
brand_header "Results"
printf "  %s%d passed%s   %s%d failed%s\n\n" "$C_GREEN_B" "$PASS" "$C_RESET" "$C_RED_B" "$FAIL" "$C_RESET"

if [[ $FAIL -eq 0 ]]; then
    brand_ok "tests/nodes.sh PASSED"
    exit 0
else
    brand_warn "tests/nodes.sh FAILED ($FAIL failures)"
    exit 1
fi
