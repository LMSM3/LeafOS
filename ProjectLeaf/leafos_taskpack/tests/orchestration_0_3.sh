#!/usr/bin/env bash
# LeafOS 0.3 three-input orchestration tests.
set -euo pipefail
export LEAF_ENABLE_TEST_MOCK_PROVIDER=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$ROOT_DIR/bin/leafctl"
FIXTURES="$ROOT_DIR/tests/fixtures/orchestration-0.3"
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fail() { echo "0.3 orchestration test FAILED: $*" >&2; exit 1; }

source "$ROOT_DIR/core/orchestration/orchestrate.sh"

RUNS="$TMPDIR_TEST/runs"
mkdir -p "$RUNS"

LEAF_ORCHESTRATION_RUNS_DIR="$RUNS" "$CLI" agent-orchestrate \
	"$FIXTURES/README.md" "$FIXTURES/skeleton.md" "$FIXTURES/wildcard.json" \
	--provider mock >/dev/null

plan_only_run="$(find "$RUNS" -mindepth 1 -maxdepth 1 -type d -name 'orchestration-*' | head -1)"
[[ -n "$plan_only_run" ]] || fail "plan-only run directory missing"
[[ -f "$plan_only_run/plan.json" ]] || fail "plan-only plan missing"
[[ ! -f "$plan_only_run/execution.jsonl" ]] || fail "plan-only mode executed actions"
orchestration_plan_validate "$plan_only_run/plan.json" || fail "mock plan failed validation"

LEAF_ORCHESTRATION_RUNS_DIR="$RUNS" "$CLI" agent-orchestrate \
	"$FIXTURES/README.md" "$FIXTURES/skeleton.md" "$FIXTURES/wildcard.json" \
	--provider mock --yes >/dev/null

executed_run="$(find "$RUNS" -mindepth 1 -maxdepth 1 -type d -name 'orchestration-*' | sort | tail -1)"
[[ -f "$executed_run/context.json" ]] || fail "context manifest missing"
[[ -f "$executed_run/report.md" ]] || fail "report missing"
[[ -f "$executed_run/execution.jsonl" ]] || fail "execution log missing"
[[ "$(jq -s 'length' "$executed_run/execution.jsonl")" -eq 6 ]] || fail "expected six executed actions"
[[ "$(jq -r 'to_entries[].value' "$executed_run/execution.state.json" | sort -u)" == "done" ]] \
	|| fail "not all actions completed"
[[ "$(jq '.inputs | keys | length' "$executed_run/context.json")" -eq 3 ]] \
	|| fail "context does not contain exactly three inputs"
[[ -s "$executed_run/artifacts/hash_wildcard.sha256" ]] || fail "wildcard hash artifact missing"
[[ -f "$executed_run/artifacts/check_cli.log" ]] || fail "verification skill artifact missing"
[[ -s "$executed_run/artifacts/read_readme.txt" ]] || fail "README read artifact missing"
[[ -s "$executed_run/artifacts/read_skeleton.txt" ]] || fail "skeleton read artifact missing"

if "$CLI" agent-orchestrate "$FIXTURES/README.md" "$FIXTURES/skeleton.md" --provider mock >/dev/null 2>&1; then
	fail "orchestrator accepted fewer than three inputs"
fi

if orchestration_plan_validate "$FIXTURES/plan-invalid.json"; then
	fail "invalid shell skill plan passed validation"
fi

echo "0.3 orchestration tests passed"
