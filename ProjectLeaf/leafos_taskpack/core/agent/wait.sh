#!/usr/bin/env bash
# core/agent/wait.sh
# Soft bounded waiting loops.
#
# "Soft" = visible, does not panic instantly.
# "Bounded" = does not sit there until the sun expands.
#
# Every wait loop has: condition, interval, max_attempts, timeout message,
# on_success indicator, on_failure indicator.

set -uo pipefail

_WAIT_ROOT="${_WAIT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_WAIT_ROOT/core/brand/brand.sh"

_WAIT_FRAMES=("❑" "❒" "❐" "❏")

_wait_tick() {
	local i="$1" target="$2"
	printf '\r  %s  %swaiting%s for %s' \
		"${_WAIT_FRAMES[$((i % 4))]}" \
		"$C_DIM" "$C_RESET" \
		"$target"
}

_wait_success() {
	printf '\r  %s⚝%s  %sready:%s %s\n' \
		"$C_GREEN_B" "$C_RESET" \
		"$C_DIM"     "$C_RESET" \
		"$1"
}

_wait_timeout() {
	printf '\r  %s⚠︎%s  %stimeout%s waiting for %s\n' \
		"$C_YELLOW_B" "$C_RESET" \
		"$C_RED"      "$C_RESET" \
		"$1" >&2
}

# ---------------------------------------------------------------------------
# leaf_wait_file TARGET [INTERVAL [MAX_ATTEMPTS]]
# Poll until TARGET exists and is non-empty.
# ---------------------------------------------------------------------------
leaf_wait_file() {
	local target="$1"
	local interval="${2:-1}"
	local max_attempts="${3:-60}"
	local i=0

	while (( i < max_attempts )); do
		if [[ -s "$target" ]]; then
			_wait_success "$target"
			return 0
		fi
		_wait_tick "$i" "$target"
		sleep "$interval"
		i=$(( i + 1 ))
	done

	_wait_timeout "$target"
	return 1
}

# ---------------------------------------------------------------------------
# leaf_wait_command CMD [INTERVAL [MAX_ATTEMPTS]]
# Poll until CMD exits 0.
# ---------------------------------------------------------------------------
leaf_wait_command() {
	local cmd="$1"
	local interval="${2:-2}"
	local max_attempts="${3:-30}"
	local i=0

	while (( i < max_attempts )); do
		if bash -c "$cmd" &>/dev/null; then
			_wait_success "$cmd"
			return 0
		fi
		_wait_tick "$i" "$cmd"
		sleep "$interval"
		i=$(( i + 1 ))
	done

	_wait_timeout "$cmd"
	return 1
}

# ---------------------------------------------------------------------------
# leaf_wait_process PID [INTERVAL [MAX_ATTEMPTS]]
# Poll until PID is no longer running.
# ---------------------------------------------------------------------------
leaf_wait_process() {
	local pid="$1"
	local interval="${2:-1}"
	local max_attempts="${3:-120}"
	local i=0

	while (( i < max_attempts )); do
		if ! kill -0 "$pid" 2>/dev/null; then
			_wait_success "process $pid"
			wait "$pid" 2>/dev/null || true
			return 0
		fi
		_wait_tick "$i" "process $pid"
		sleep "$interval"
		i=$(( i + 1 ))
	done

	_wait_timeout "process $pid"
	return 1
}

# ---------------------------------------------------------------------------
# leaf_wait_node NODE_JSON_FILE
# Dispatch wait based on the "wait" block embedded in a node JSON file.
# NODE_JSON_FILE is a temp file containing the node object.
# ---------------------------------------------------------------------------
leaf_wait_node() {
	local node_file="$1"
	command -v jq &>/dev/null || { brand_warn "jq required for wait dispatch"; return 1; }

	local enabled; enabled="$(jq -r '.wait.enabled // "false"' "$node_file")"
	[[ "$enabled" == "true" ]] || return 0

	local condition; condition="$(jq -r '.wait.condition // ""'  "$node_file")"
	local target;    target="$(jq -r    '.wait.target // ""'     "$node_file")"
	local interval;  interval="$(jq -r  '.wait.interval_seconds // 1' "$node_file")"
	local maxatt;    maxatt="$(jq -r    '.wait.max_attempts // 60'     "$node_file")"

	case "$condition" in
		patch_file_exists|file_exists|require_file)
			leaf_wait_file "$target" "$interval" "$maxatt"
			;;
		command_success)
			leaf_wait_command "$target" "$interval" "$maxatt"
			;;
		process_done)
			leaf_wait_process "$target" "$interval" "$maxatt"
			;;
		*)
			brand_warn "unknown wait condition '$condition' — skipping wait"
			;;
	esac
}
