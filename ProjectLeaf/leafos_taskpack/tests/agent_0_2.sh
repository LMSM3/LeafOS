#!/usr/bin/env bash
# LeafOS 0.2 checklist regression tests.
set -euo pipefail
export LEAF_ENABLE_TEST_MOCK_PROVIDER=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$ROOT_DIR/bin/leafctl"
FIXTURES="$ROOT_DIR/tests/fixtures/agent-0.2"
TAG="agent-0-2-${BASHPID}"
TASK_TITLE="LeafOS 0.2 $BASHPID & parser"

fail() { echo "0.2 test FAILED: $*" >&2; exit 1; }

source "$ROOT_DIR/core/agent/agent.sh"

slug="$(agent_slug 'Hello, World! / Alpha_0.2')"
[[ "$slug" == 'hello-world-alpha-0-2' ]] || fail "unexpected slug normalization: $slug"

task_slug="$(agent_slug "$TASK_TITLE")"
task_path="$ROOT_DIR/tasks/$task_slug.md"
plan_path="$ROOT_DIR/tasks/$task_slug.provider-test.plan.sh"
template_plan_path="$ROOT_DIR/tasks/$task_slug.template-test.plan.sh"
parser_task_path="$ROOT_DIR/tasks/$TAG-parser.md"
parser_plan_path="$ROOT_DIR/tasks/$TAG-parser.provider-test.plan.sh"
report_path="$ROOT_DIR/reports/$TAG.md"

cleanup() {
    rm -f "$task_path" "$plan_path" "$template_plan_path" \
        "$parser_task_path" "$parser_plan_path" "$report_path"
}
trap cleanup EXIT

"$CLI" agent-task "$TASK_TITLE" >/dev/null
[[ -f "$task_path" ]] || fail "task file was not created"
agent_task_validate "$task_path" || fail "generated task failed validation"
for section in Title Scope Steps; do
    grep -q "^## $section$" "$task_path" || fail "task missing section: $section"
done

if "$CLI" agent-task "$TASK_TITLE" >/dev/null 2>&1; then
    fail "agent-task overwrote an existing task"
fi

"$CLI" agent-plan "tasks/$task_slug.md" 'template test' >/dev/null
[[ -f "$template_plan_path" ]] || fail "template plan was not created"
grep -q '^# LEAFOS_AGENT_PLAN_VERSION=0.2.0$' "$template_plan_path" \
    || fail "template plan missing version metadata"
"$CLI" agent-validate "tasks/$task_slug.template-test.plan.sh" >/dev/null \
    || fail "template plan failed validation"

cp "$FIXTURES/task-parser.md" "$parser_task_path"
"$CLI" agent-route "tasks/$TAG-parser.md" provider-test --provider mock >/dev/null
[[ -f "$parser_plan_path" ]] || fail "mock provider plan was not created"
grep -q '^# LEAFOS_AGENT_PLAN_VERSION=0.2.0$' "$parser_plan_path" \
    || fail "mock plan missing version metadata"
grep -q 'quoted' "$parser_plan_path" || fail "mock parser lost quoted step data"
"$CLI" agent-validate "tasks/$TAG-parser.provider-test.plan.sh" >/dev/null \
    || fail "mock plan failed validation"

normal_out="$($CLI agent-dry-run "tasks/$TAG-parser.provider-test.plan.sh")"
grep -q 'would run' <<< "$normal_out" || fail "normal dry-run output missing preview lines"

plain_out="$($CLI agent-dry-run "tasks/$TAG-parser.provider-test.plan.sh" --plain)"
if grep -q 'dry-run plan:' <<< "$plain_out"; then
    fail "plain dry-run output contains normal-mode header"
fi
[[ -n "$plain_out" ]] || fail "plain dry-run output was empty"

json_out="$($CLI agent-dry-run "tasks/$TAG-parser.provider-test.plan.sh" --json)"
if command -v python3 >/dev/null 2>&1; then
    JSON_OUT="$json_out" python3 -c 'import json, os; value=json.loads(os.environ["JSON_OUT"]); assert value["steps"]'
else
    grep -q '"plan"' <<< "$json_out" || fail "JSON dry-run output missing plan field"
fi

safe_plan="$FIXTURES/plan-safe.sh"
if "$CLI" agent-run "$safe_plan" >/dev/null 2>&1; then
    fail "agent-run executed without --yes"
else
    rc=$?
    [[ "$rc" -eq 3 ]] || fail "agent-run guard returned $rc instead of 3"
fi
"$CLI" agent-run "$safe_plan" --yes >/dev/null || fail "confirmed safe plan failed"

if "$CLI" agent-validate "$FIXTURES/plan-dangerous.sh" >/dev/null 2>&1; then
    fail "destructive plan passed validation"
fi

"$CLI" agent-report "$TAG" >/dev/null
[[ -f "$report_path" ]] || fail "report path was not written"

echo "0.2 checklist tests passed"
