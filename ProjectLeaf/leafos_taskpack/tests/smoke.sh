#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$ROOT_DIR/tests/cli_strict.sh"
"$ROOT_DIR/bin/leafctl" doctor
"$ROOT_DIR/bin/leafctl" status >/tmp/leafos_status.out
grep -q "LeafOS" /tmp/leafos_status.out
grep -q "orbit" <<< "$("$ROOT_DIR/bin/leafctl" loaders)"
bash "$ROOT_DIR/tests/runtime.sh" >/tmp/leafos_runtime.out
"$ROOT_DIR/bin/build_c_demo.sh" >/tmp/leafos_build.out
[[ -x "$ROOT_DIR/build/leaf_loader_demo" || -x "$ROOT_DIR/build/leaf_loader_demo.exe" ]]

grep -q "local-coder" <<< "$("$ROOT_DIR/bin/leafctl" agents)"
TASK_PATH="$ROOT_DIR/tasks/smoke-agent-task.md"
PLAN_PATH="$ROOT_DIR/tasks/smoke-agent-task.default.plan.sh"
rm -f "$TASK_PATH" "$PLAN_PATH"
"$ROOT_DIR/bin/leafctl" agent-task "smoke agent task" >/tmp/leafos_agent_task.out
[[ -f "$TASK_PATH" ]]
"$ROOT_DIR/bin/leafctl" agent-plan "tasks/smoke-agent-task.md" default >/tmp/leafos_agent_plan.out
[[ -f "$PLAN_PATH" ]]
"$ROOT_DIR/bin/leafctl" agent-validate "tasks/smoke-agent-task.default.plan.sh" >/tmp/leafos_agent_validate.out
grep -q "would run" <<< "$("$ROOT_DIR/bin/leafctl" agent-dry-run-file "tasks/smoke-agent-task.default.plan.sh")"
"$ROOT_DIR/bin/leafctl" agent-report smoke >/tmp/leafos_agent_report.out
echo "smoke tests passed"
