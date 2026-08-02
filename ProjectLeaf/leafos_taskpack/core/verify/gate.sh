#!/usr/bin/env bash
# core/verify/gate.sh
# Completion gate. The project is not "done" because the model sounds proud.
#
# Checks:
#   1. required_files     — each must exist and be non-empty
#   2. required_commands  — each must exit 0
#   3. forbidden_paths    — none may have been touched (git diff guard)
#
# Gate spec lives in .completion_gate of agent.graph.json.

set -uo pipefail

_GATE_ROOT="${_GATE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_GATE_ROOT/core/brand/brand.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_GATE_ROOT/runs}"

# ---------------------------------------------------------------------------
# gate_run GRAPH_FILE [WORKDIR]
# Read completion_gate from graph and run all checks.
# Returns 0 if gate passes, 1 if any check fails.
# ---------------------------------------------------------------------------
gate_run() {
	local graph="${1:-$LEAF_RUNS_DIR/latest/agent.graph.json}"
	local workdir="${2:-$_GATE_ROOT}"

	command -v jq &>/dev/null || {
		brand_die "gate_run: jq is required."
	}

	[[ -f "$graph" ]] || {
		brand_warn "gate_run: graph not found: $graph"
		return 1
	}

	local failed=0

	brand_header "ꕤ completion gate"
	brand_kv "graph"   "$graph"
	brand_kv "workdir" "$workdir"
	printf '\n'

	# -- 1. Required files ---------------------------------------------------
	local req_files
	mapfile -t req_files < <(
		jq -r '.completion_gate.required_files[]? // empty' "$graph"
	)

	if [[ ${#req_files[@]} -gt 0 ]]; then
		brand_step 1 "required files"
		local f
		for f in "${req_files[@]}"; do
			local full="${workdir}/${f#/}"
			if [[ -s "$full" ]]; then
				brand_ok "  $f"
			else
				brand_warn "  missing or empty: $f"
				failed=$(( failed + 1 ))
			fi
		done
		printf '\n'
	fi

	# -- 2. Required commands ------------------------------------------------
	local req_cmds
	mapfile -t req_cmds < <(
		jq -r '.completion_gate.required_commands[]? // empty' "$graph"
	)

	if [[ ${#req_cmds[@]} -gt 0 ]]; then
		brand_step 2 "required commands"
		local cmd
		for cmd in "${req_cmds[@]}"; do
			if (cd "$workdir" && bash -c "$cmd" &>/dev/null); then
				brand_ok "  $cmd"
			else
				brand_warn "  failed: $cmd"
				failed=$(( failed + 1 ))
			fi
		done
		printf '\n'
	fi

	# -- 3. Forbidden paths --------------------------------------------------
	local forbidden_paths
	mapfile -t forbidden_paths < <(
		jq -r '.completion_gate.forbidden_paths[]? // empty' "$graph"
	)

	if [[ ${#forbidden_paths[@]} -gt 0 ]] && command -v git &>/dev/null; then
		brand_step 3 "forbidden paths"
		local changed_files
		mapfile -t changed_files < <(
			git -C "$workdir" diff --name-only HEAD 2>/dev/null || true
		)
		local fp touched
		for fp in "${forbidden_paths[@]}"; do
			# Check if any changed file starts with the forbidden path prefix
			touched=""
			local cf
			for cf in "${changed_files[@]}"; do
				if [[ "$cf" == "${fp}"* ]] || [[ "$cf" == *"${fp}"* ]]; then
					touched="$cf"
					break
				fi
			done
			if [[ -n "$touched" ]]; then
				brand_warn "  forbidden path touched: $fp (by $touched)"
				failed=$(( failed + 1 ))
			else
				brand_ok "  $fp — clear"
			fi
		done
		printf '\n'
	fi

	# -- Result --------------------------------------------------------------
	if [[ $failed -eq 0 ]]; then
		brand_ok "⚝  gate passed."
		return 0
	else
		brand_warn "⚠︎  gate failed: $failed check(s) did not pass."
		return 1
	fi
}

# ---------------------------------------------------------------------------
# gate_print GRAPH_FILE
# Print the completion criteria without running them.
# ---------------------------------------------------------------------------
gate_print() {
	local graph="${1:-$LEAF_RUNS_DIR/latest/agent.graph.json}"
	command -v jq &>/dev/null || { brand_warn "jq required"; return 1; }
	[[ -f "$graph" ]] || { brand_warn "graph not found: $graph"; return 1; }

	brand_header "ꕤ completion gate spec"
	printf '\n  %sRequired files:%s\n' "$C_BOLD" "$C_RESET"
	jq -r '.completion_gate.required_files[]? // empty | "    " + .' "$graph"
	printf '\n  %sRequired commands:%s\n' "$C_BOLD" "$C_RESET"
	jq -r '.completion_gate.required_commands[]? // empty | "    " + .' "$graph"
	printf '\n  %sForbidden paths:%s\n' "$C_BOLD" "$C_RESET"
	jq -r '.completion_gate.forbidden_paths[]? // empty | "    " + .' "$graph"
	printf '\n'
}
