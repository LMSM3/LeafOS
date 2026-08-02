#!/usr/bin/env bash
# LEAFOS_AGENT_PLAN=1
# LEAFOS_AGENT_PLAN_VERSION=0.2.0
# Fixture: safe plan

set -euo pipefail

run_step() {
    "$@"
}

run_step printf '%s\n' 'safe fixture executed'
