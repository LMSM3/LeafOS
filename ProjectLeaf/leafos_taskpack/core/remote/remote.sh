#!/usr/bin/env bash
# core/remote/remote.sh -- distributor-side transport + registry + task verbs.
# Transports: local (same box, another LEAF_HOME) and ssh (user@host).
set -u
_REMOTE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_REMOTE_DIR/../node/node.sh"

_node_resolve() {
    local name="$1"
    _RT="$(leaf_node_engine registry-get "$name" --field transport)" || return 1
    _RTGT="$(leaf_node_engine registry-get "$name" --field target)"
    _RPATH="$(leaf_node_engine registry-get "$name" --field path)"
    [[ -n "$_RT" ]] || _RT="ssh"
    [[ -n "$_RPATH" ]] || _RPATH="~/.leaf"
    return 0
}

_ssh() { ssh ${LEAF_SSH_OPTS:-} "$@"; }
_scp() { scp ${LEAF_SSH_OPTS:-} "$@"; }
_remote_cmd() { printf "%s" "${LEAF_REMOTE_CMD:-leaf}"; }

_local_engine() { local py; py="$(_leaf_py)"; LEAF_HOME="$_RPATH" "$py" "$LEAF_NODE_PY" "$@"; }

_remote_status() {
    local name="$1"
    _node_resolve "$name" || brand_die "unknown node: $name"
    case "$_RT" in
        local) _local_engine status --json ;;
        ssh)   _ssh "$_RTGT" "$(_remote_cmd) node status --json" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

_remote_push_inbox() {
    local name="$1" src="$2" task_id="$3"
    _node_resolve "$name" || brand_die "unknown node: $name"
    case "$_RT" in
        local) mkdir -p "$_RPATH/inbox"; cp "$src" "$_RPATH/inbox/$task_id.json" ;;
        ssh)   _scp "$src" "$_RTGT:$_RPATH/inbox/$task_id.json" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

_remote_start() {
    local name="$1" task_id="$2"
    _node_resolve "$name" || brand_die "unknown node: $name"
    case "$_RT" in
        local) _local_engine task-start "$task_id" ;;
        ssh)   _ssh "$_RTGT" "$(_remote_cmd) task start $task_id" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

_remote_tail() {
    local name="$1" task_id="$2"
    _node_resolve "$name" || brand_die "unknown node: $name"
    case "$_RT" in
        local) _local_engine task-logs "$task_id" --follow ;;
        ssh)   _ssh "$_RTGT" "tail -n +1 -f $_RPATH/logs/$task_id.jsonl" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

_remote_pull_results() {
    local name="$1" task_id="$2" dest="$3"
    _node_resolve "$name" || brand_die "unknown node: $name"
    mkdir -p "$dest"
    case "$_RT" in
        local) cp -r "$_RPATH/results/$task_id" "$dest/" ;;
        ssh)   _scp -r "$_RTGT:$_RPATH/results/$task_id" "$dest/" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

_remote_cancel() {
    local name="$1" task_id="$2"
    _node_resolve "$name" || brand_die "unknown node: $name"
    case "$_RT" in
        local) _local_engine task-cancel "$task_id" ;;
        ssh)   _ssh "$_RTGT" "$(_remote_cmd) task cancel $task_id" ;;
        *)     brand_die "unknown transport: $_RT" ;;
    esac
}

leaf_nodes_add() {
    local name="${1:-}" target="${2:-}"; shift 2 2>/dev/null || true
    [[ -n "$name" && -n "$target" ]] || brand_die "nodes add requires NAME USER@HOST"
    brand_header "nodes add"
    leaf_node_engine registry-add "$name" "$target" "$@"
    brand_ok "registered node $name -> $target"
}

leaf_nodes_list() {
    _has_json "$@" || brand_header "nodes"
    leaf_node_engine registry-list "$@"
}

leaf_nodes_ping() {
    local name="${1:-}"; [[ -n "$name" ]] || brand_die "nodes ping requires NAME"
    brand_say "pinging $name"
    if _remote_status "$name"; then brand_ok "$name reachable"; else brand_die "$name unreachable"; fi
}

leaf_task_submit() {
    local name="${1:-}" file="${2:-}"
    [[ -n "$name" && -n "$file" ]] || brand_die "task submit requires NAME TASK_FILE"
    [[ -f "$file" ]] || brand_die "task file not found: $file"
    brand_header "task submit -> $name"
    local task_id; task_id="$(leaf_node_engine new-task-id)"
    local stamped; stamped="$(mktemp 2>/dev/null || printf "%s" "${TMPDIR:-/tmp}/leaf_$task_id.json")"
    leaf_node_engine stamp-task "$file" "$stamped" --task-id "$task_id" >/dev/null
    _remote_push_inbox "$name" "$stamped" "$task_id"
    rm -f "$stamped"
    brand_say "queued $task_id on $name"
    _remote_start "$name" "$task_id"
    brand_ok "submitted $task_id"
    printf "%s\n" "$task_id"
}

leaf_task_watch() {
    local name="${1:-}" task_id="${2:-}"
    [[ -n "$name" && -n "$task_id" ]] || brand_die "task watch requires NAME TASK_ID"
    brand_header "task watch $task_id"
    _remote_tail "$name" "$task_id"
}

leaf_task_pull() {
    local name="${1:-}" task_id="${2:-}" dest="${3:-./results}"
    [[ -n "$name" && -n "$task_id" ]] || brand_die "task pull requires NAME TASK_ID"
    brand_header "task pull $task_id"
    _remote_pull_results "$name" "$task_id" "$dest"
    brand_ok "results -> $dest/$task_id"
}

leaf_task_cancel() {
    local name="${1:-}" task_id="${2:-}"
    [[ -n "$name" && -n "$task_id" ]] || brand_die "task cancel requires NAME TASK_ID"
    brand_header "task cancel $task_id"
    _remote_cancel "$name" "$task_id"
}
