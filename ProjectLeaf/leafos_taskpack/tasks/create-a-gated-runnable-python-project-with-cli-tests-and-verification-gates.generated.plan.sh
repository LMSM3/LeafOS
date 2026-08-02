#!/usr/bin/env bash
# LEAFOS_AGENT_PLAN=1
# LEAFOS_AGENT_PLAN_VERSION=0.2.0
# Generated:  2026-07-12T09:13:44Z
# Task:       /c/R/LeafOS0.2.1/ProjectLeaf/leafos_taskpack/tasks/create-a-gated-runnable-python-project-with-cli-tests-and-verification-gates.md
# Title:      create a gated runnable Python project with CLI, tests, and verification gates
# Scope:      Describe the smallest useful coding outcome.;Keep changes auditable and reversible.
# Provider:   mock (offline)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

run_step() { printf 'agent-step: %s\n' "$*"; "$@"; }

run_step "/c/R/LeafOS0.2.1/ProjectLeaf/leafos_taskpack/bin/leafctl" doctor
run_step "/c/R/LeafOS0.2.1/ProjectLeaf/leafos_taskpack/tests/smoke.sh"
run_step printf "step: %s\n" Implement\ the\ task.
run_step "/c/R/LeafOS0.2.1/ProjectLeaf/leafos_taskpack/tests/smoke.sh"

