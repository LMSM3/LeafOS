#!/usr/bin/env bash
# LEAFOS_AGENT_PLAN=1
# LEAFOS_AGENT_PLAN_VERSION=0.2.0
# Created: {{CREATED_AT}}
# Task: {{TASK_FILE}}
# Task-Slug: {{TASK_SLUG}}
# Plan-Name: {{PLAN_NAME}}
# Provider: template
#
# Agent command plan.
# Review with:
#   ./bin/leafctl agent-dry-run THIS_FILE
# Execute with:
#   ./bin/leafctl agent-run THIS_FILE --yes

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_step() {
    printf 'agent-step: %s\n' "$*"
    "$@"
}

run_step "$ROOT_DIR/bin/leafctl" doctor
run_step "$ROOT_DIR/bin/leafctl" status
run_step "$ROOT_DIR/tests/smoke.sh"
