#!/usr/bin/env bash
# core/agent/loop.sh
# Graph execution loop: pick → run → update → repair → gate
#
# Symbols used during execution:
#   𔓘  load graph
#   🍃  activate runtime
#   ❦  select next node
#   ⋆  run embedded agent action
#   ❑❒❐❏  wait softly
#   𓂃  apply result
#   ⚠︎  repair if failed
#   ⚝  verify if passed
#   ⎙  append report
#   ꕤ  checkpoint when complete

set -uo pipefail

_LOOP_ROOT="${_LOOP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_LOOP_ROOT/core/brand/brand.sh"
source "$_LOOP_ROOT/core/loaders/loaders.sh"
source "$_LOOP_ROOT/core/graph/graph.sh"
source "$_LOOP_ROOT/core/agent/actions.sh"
source "$_LOOP_ROOT/core/agent/repair.sh"
source "$_LOOP_ROOT/core/verify/gate.sh"

LOOP_MAX_ITERATIONS="${LOOP_MAX_ITERATIONS:-40}"
LOOP_APPLY="${LOOP_APPLY:-0}"        # 1 = actually apply patches / writes
LOOP_SOFT_WAIT="${LOOP_SOFT_WAIT:-1}" # 1 = honour .wait blocks in nodes
LOOP_YES="${LOOP_YES:-0}"            # 1 = skip confirmation prompts

# ---------------------------------------------------------------------------
# _loop_run_node GRAPH_FILE NODE_ID
# Extracts node JSON, dispatches to agent_run_action, returns exit code.
# ---------------------------------------------------------------------------
_loop_run_node() {
	local graph="$1"
	local node_id="$2"

	local node_json; node_json="$(jq -r --arg id "$node_id" '.nodes[] | select(.id == $id)' "$graph")"
	local action;    action="$(jq -r    '.action // .type'      <<< "$node_json")"
	local actor;     actor="$(jq -r     '.actor // "system"'    <<< "$node_json")"
	local symbol;    symbol="$(jq -r    '.symbol // "❦"'        <<< "$node_json")"
	local input_json; input_json="$(jq  '.input // {}'          <<< "$node_json")"

	printf '\n  %s%s%s  %s❦ %s%s  (%s · %s)\n' \
		"$C_CYAN_B" "$symbol" "$C_RESET" \
		"$C_BOLD"   "$node_id" "$C_RESET" \
		"$actor" "$action"

	graph_set_status "$graph" "$node_id" "running"

	# Honour embedded wait block before running action
	if [[ "$LOOP_SOFT_WAIT" == "1" ]]; then
		local tmp_node; tmp_node="$(mktemp)"
		printf '%s\n' "$node_json" > "$tmp_node"
		leaf_wait_node "$tmp_node" || true
		rm -f "$tmp_node"
	fi

	# Dispatch action
	if agent_run_action "$action" "$node_id" "$input_json"; then
		graph_set_status "$graph" "$node_id" "done"
		brand_ok "⚝  $node_id — done"
		return 0
	else
		local rc=$?
		graph_set_status "$graph" "$node_id" "failed"
		brand_warn "⚠︎  $node_id — failed (exit $rc)"
		return $rc
	fi
}

# ---------------------------------------------------------------------------
# agent_loop_run GRAPH_FILE [--apply] [--yes] [--soft-wait] [--no-wait]
# Main loop entry point.
# ---------------------------------------------------------------------------
agent_loop_run() {
	local graph="${1:-$LEAF_RUN_DIR/agent.graph.json}"
	shift || true

	# Parse flags
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--apply)     LOOP_APPLY=1 ;;
			--yes)       LOOP_YES=1 ;;
			--soft-wait) LOOP_SOFT_WAIT=1 ;;
			--no-wait)   LOOP_SOFT_WAIT=0 ;;
			*) brand_warn "agent_loop_run: unknown flag $1" ;;
		esac
		shift
	done

	[[ -f "$graph" ]] || brand_die "graph not found: $graph"

	brand_banner
	brand_header "𔓘 loading graph"
	graph_print "$graph"

	if [[ "$LOOP_YES" != "1" ]]; then
		printf '\n  %s▶ Run this graph? [y/N]%s ' "$C_BOLD" "$C_RESET"
		local ans; read -r ans
		[[ "${ans:-n}" == [yY] ]] || { brand_say "loop cancelled."; return 0; }
	fi

	brand_header "🍃 activating runtime"
	brand_kv "graph"      "$graph"
	brand_kv "max_iter"   "$LOOP_MAX_ITERATIONS"
	brand_kv "apply"      "$LOOP_APPLY"
	brand_kv "soft_wait"  "$LOOP_SOFT_WAIT"
	printf '\n'

	local iteration=0
	local report_file; report_file="$(dirname "$graph")/report.md"

	{
		printf '# LeafOS Run Report\n\n'
		printf 'graph: %s\n' "$graph"
		printf 'started: %s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	} > "$report_file"

	while graph_has_pending "$graph"; do
		iteration=$(( iteration + 1 ))

		if (( iteration > LOOP_MAX_ITERATIONS )); then
			brand_warn "⚠︎  max iterations ($LOOP_MAX_ITERATIONS) reached — stopping."
			printf '\n## Loop aborted\n\nmax_iterations reached.\n' >> "$report_file"
			return 1
		fi

		local node_id; node_id="$(graph_next_ready "$graph")"

		if [[ -z "$node_id" ]]; then
			brand_warn "⚠︎  no ready node found but pending nodes remain — dependency deadlock?"
			printf '\n## Loop error\n\nDeadlock: pending nodes with unsatisfied deps.\n' >> "$report_file"
			return 1
		fi

		if _loop_run_node "$graph" "$node_id"; then
			printf '\n## %s — ⚝ done\n\n' "$node_id" >> "$report_file"
			action_report_append "$node_id" "{\"message\":\"node $node_id completed successfully\"}"
		else
			printf '\n## %s — ⚠︎ failed\n\n' "$node_id" >> "$report_file"
			brand_warn "Creating repair node for failed node: $node_id"
			repair_create_node "$graph" "$node_id" "action failed"
		fi

		# Run gate after every node to check for early completion
		if gate_run "$graph" 2>/dev/null; then
			brand_ok "ꕤ  completion gate passed — graph complete."
			printf '\n## Completion gate\n\n⚝ passed after %d iterations.\n' "$iteration" >> "$report_file"
			# Mark any remaining pending nodes as skipped
			jq -r '.nodes[] | select(.status == "pending") | .id' "$graph" \
			| while read -r nid; do
				graph_set_status "$graph" "$nid" "skipped"
			  done
			break
		fi
	done

	printf '\n## Summary\n\n' >> "$report_file"
	jq -r '.nodes[] | "- \(.id): \(.status)"' "$graph" >> "$report_file"

	printf '\n'
	brand_header "⎙ loop complete"
	graph_print "$graph"
	brand_kv "report" "$report_file"

	gate_run "$graph" || brand_warn "Gate did not pass at loop end."
}
