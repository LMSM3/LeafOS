#!/usr/bin/env bash
# core/node/node.sh -- receiver-side (worker) node commands.
# Thin brand-aware wrapper over the python node engine (leaf_node.py).
set -u
_NODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_NODE_DIR/../system/paths.sh"
source "$_NODE_DIR/../brand/brand.sh"

LEAF_NODE_PY="$_NODE_DIR/leaf_node.py"

_leaf_py() {
    local py=""
    for cand in python3 python; do
        if command -v "$cand" >/dev/null 2>&1; then py="$cand"; break; fi
    done
    [[ -n "$py" ]] || brand_die "python3 not found (node engine requires Python 3.8+)"
    printf "%s" "$py"
}

# leaf_node_engine ARGS... -- invoke the python engine directly
leaf_node_engine() {
    local py; py="$(_leaf_py)"
    "$py" "$LEAF_NODE_PY" "$@"
}

# _has_json FLAG... -- true if any arg is --json (suppress branding for machine output)
_has_json() {
    local a
    for a in "$@"; do [[ "$a" == "--json" ]] && return 0; done
    return 1
}

leaf_node_init() {
    _has_json "$@" || brand_header "node init"
    leaf_node_engine init "$@"
}

leaf_node_status() {
    _has_json "$@" || brand_header "node status"
    leaf_node_engine status "$@"
}

leaf_node_hardware() {
    _has_json "$@" || brand_header "hardware probe"
    leaf_node_engine hardware "$@"
}

# leaf_task_start TASK_ID -- run a task already present in the workspace
leaf_task_start() {
    local task_id="${1:-}"
    [[ -n "$task_id" ]] || brand_die "task start requires TASK_ID"
    brand_say "starting task $task_id"
    leaf_node_engine task-start "$task_id"
}

leaf_task_list() { leaf_node_engine task-list "$@"; }
leaf_task_logs() { leaf_node_engine task-logs "$@"; }
leaf_task_result() { leaf_node_engine task-result "$@"; }
leaf_task_cancel_local() { leaf_node_engine task-cancel "$@"; }
