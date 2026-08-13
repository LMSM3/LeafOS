#!/usr/bin/env bash
# Runtime logging helpers.

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/system/paths.sh"
mkdir -p "$LEAF_LOG_DIR"

leaf_ts() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

leaf_log() {
    local level="${1:-INFO}"
    shift || true
    local msg="$*"
    printf '%s\t%s\t%s\n' "$(leaf_ts)" "$level" "$msg" >> "$LEAF_LOG_DIR/session.log"
}

leaf_event() {
    local kind="${1:-event}"
    shift || true
    local msg="$*"
    msg=${msg//\\/\\\\}
    msg=${msg//\"/\\\"}
    printf '{"time":"%s","kind":"%s","message":"%s"}\n' \
        "$(leaf_ts)" "$kind" "$msg" >> "$LEAF_LOG_DIR/events.jsonl"
}
