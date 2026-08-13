#!/usr/bin/env bash
# LeafOS 0.4 embedded action result artifact tests.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

export _ACTIONS_ROOT="$ROOT_DIR"
export LEAF_RUN_DIR="$TMPDIR_TEST/run"
source "$ROOT_DIR/core/agent/actions.sh"

TARGET="$TMPDIR_TEST/required.txt"
printf 'ready\n' > "$TARGET"

success_input="$(jq -n --arg target "$TARGET" '{target: $target}')"
agent_run_action fs.require_file node-success "$success_input" >/dev/null
success_result="$LEAF_RUN_DIR/action-results/node-success.json"
[[ -f "$success_result" ]] || { echo "missing success result artifact" >&2; exit 1; }
[[ "$(jq -r '.status' "$success_result")" == 'passed' ]] || { echo "success result status incorrect" >&2; exit 1; }
[[ "$(jq -r '.exit_code' "$success_result")" == '0' ]] || { echo "success result exit code incorrect" >&2; exit 1; }

failure_input="$(jq -n --arg target "$TMPDIR_TEST/missing.txt" '{target: $target}')"
if agent_run_action fs.require_file node-failure "$failure_input" >/dev/null 2>&1; then
	echo "missing file action unexpectedly passed" >&2
	exit 1
fi
failure_result="$LEAF_RUN_DIR/action-results/node-failure.json"
[[ -f "$failure_result" ]] || { echo "missing failure result artifact" >&2; exit 1; }
[[ "$(jq -r '.status' "$failure_result")" == 'failed' ]] || { echo "failure result status incorrect" >&2; exit 1; }
[[ "$(jq -r '.exit_code' "$failure_result")" != '0' ]] || { echo "failure result exit code incorrect" >&2; exit 1; }

# Coder and dual-thinking actions fail closed when no valid task artifact exists.
coder_input='{"task":"implement a bounded change"}'
if agent_run_action agent.ask_coder coder-missing "$coder_input" >/dev/null 2>&1; then
	echo "coder action unexpectedly passed without a valid patch" >&2
	exit 1
fi
coder_result="$LEAF_RUN_DIR/action-results/coder-missing.json"
[[ "$(jq -r '.stream' "$coder_result")" == 'coder' ]] || { echo "coder stream metadata missing" >&2; exit 1; }

if agent_run_action agent.dual_think dual-missing '{}' >/dev/null 2>&1; then
	echo "dual action unexpectedly passed without task_file" >&2
	exit 1
fi
dual_result="$LEAF_RUN_DIR/action-results/dual-missing.json"
[[ "$(jq -r '.stream' "$dual_result")" == 'dual' ]] || { echo "dual stream metadata missing" >&2; exit 1; }
[[ "$(jq -r '.status' "$dual_result")" == 'failed' ]] || { echo "dual failure status incorrect" >&2; exit 1; }
[[ ! -e "$LEAF_RUN_DIR/applied" ]] || { echo "dual action applied changes unexpectedly" >&2; exit 1; }

echo "dual-stream action result artifacts passed"
