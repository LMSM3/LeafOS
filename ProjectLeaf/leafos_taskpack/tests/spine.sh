#!/usr/bin/env bash
# tests/spine.sh
# LeafOS 0.2.0 success condition.
#
# Proves the universal CLI task pipeline end to end, with no API key.
# Pass = 0.2.0 spine is operational.
#
#   agent-task -> gated test provider -> agent-dry-run -> agent-run --yes -> agent-report
set -euo pipefail
export LEAF_ENABLE_TEST_MOCK_PROVIDER=1

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="$ROOT_DIR/bin/leafctl"
fail() { echo "spine test FAILED: $*" >&2; exit 1; }

SLUG="spine-test-hello-c-project"
TASK_FILE="$ROOT_DIR/tasks/$SLUG.md"
PLAN_FILE="$ROOT_DIR/tasks/$SLUG.generated.plan.sh"
REPORT_DIR="$ROOT_DIR/reports"

# Clean up any leftovers from a prior run.
rm -f "$TASK_FILE" "$PLAN_FILE"

# ------------------------------------------------------------------
# Stage 1: agent-task
# Human asks. LeafOS makes a task file.
# We write a minimal task so the mock generates only safe steps
# (doctor + status) without pulling in the C build smoke suite.
# ------------------------------------------------------------------
"$CLI" agent-task "spine test hello c project" > /dev/null
[[ -f "$TASK_FILE" ]] || fail "task file not created: $TASK_FILE"
grep -q '## Title'  "$TASK_FILE" || fail "task file missing ## Title"
grep -q '## Scope'  "$TASK_FILE" || fail "task file missing ## Scope"
grep -q '## Steps'  "$TASK_FILE" || fail "task file missing ## Steps"

# Replace the generated Steps section with lightweight steps so agent-run
# does not invoke the C build smoke suite (cc may not be in PATH here).
awk '
    /^## Steps$/ { print; print ""; print "1. Check doctor status"; print "2. Print platform info"; print ""; skip=1; next }
    skip && /^## / { skip=0 }
    !skip { print }
' "$TASK_FILE" > "$TASK_FILE.tmp" && mv "$TASK_FILE.tmp" "$TASK_FILE"
echo "stage 1 ok: task created"

# ------------------------------------------------------------------
# Stage 2: explicitly gated test-provider route
# The fixture route proves plumbing and generates a filled, validated plan.
# ------------------------------------------------------------------
"$CLI" agent-route "tasks/$SLUG.md" --provider mock > /dev/null
[[ -f "$PLAN_FILE" ]] || fail "plan file not created: $PLAN_FILE"
[[ -x "$PLAN_FILE" ]] || fail "plan file not executable"
bash -n "$PLAN_FILE"  || fail "plan file has syntax errors"
grep -q 'LEAFOS_AGENT_PLAN=1' "$PLAN_FILE" || fail "plan missing LEAFOS_AGENT_PLAN marker"
echo "stage 2 ok: plan generated via gated test provider"

# ------------------------------------------------------------------
# Stage 3: agent-dry-run
# Preview before touching anything.
# ------------------------------------------------------------------
dry="$("$CLI" agent-dry-run "tasks/$SLUG.generated.plan.sh")"
echo "$dry" | grep -q 'would run' || fail "dry-run produced no 'would run' lines"
echo "stage 3 ok: dry-run previewed"

# ------------------------------------------------------------------
# Stage 4: agent-validate
# Belt and suspenders: validation must pass before we run.
# ------------------------------------------------------------------
"$CLI" agent-validate "tasks/$SLUG.generated.plan.sh" > /dev/null \
	|| fail "agent-validate failed on generated plan"
echo "stage 4 ok: plan validated"

# ------------------------------------------------------------------
# Stage 5: agent-run --yes
# Execute with explicit consent.
# ------------------------------------------------------------------
"$CLI" agent-run "tasks/$SLUG.generated.plan.sh" --yes > /dev/null \
	|| fail "agent-run failed"
echo "stage 5 ok: plan executed"

# ------------------------------------------------------------------
# Stage 6: agent-report
# Report records what happened.
# ------------------------------------------------------------------
report_out="$("$CLI" agent-report "spine-0.2.0")"
report_path="$(echo "$report_out" | grep -v '^\[LeafOS\]' | tail -1 || true)"
# Report dir must exist and contain at least one file.
[[ -d "$REPORT_DIR" ]] || fail "report directory missing"
find "$REPORT_DIR" -name 'spine-0.2.0.md' | grep -q . || fail "spine-0.2.0 report not written"
echo "stage 6 ok: report written"

# ------------------------------------------------------------------
# Clean up.
# ------------------------------------------------------------------
rm -f "$TASK_FILE" "$PLAN_FILE"

echo ""
echo "0.2.0 spine: all stages passed"
echo "  agent-task -> gated test provider -> agent-dry-run -> agent-run --yes -> agent-report"
