#!/usr/bin/env bash
# core/agent/repair.sh
# Repair node injection. When a node fails the loop calls repair_create_node,
# which appends a new "repair" node that depends on the failed node and will be
# picked up on the next loop iteration.

set -uo pipefail

_REPAIR_ROOT="${_REPAIR_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_REPAIR_ROOT/core/brand/brand.sh"
source "$_REPAIR_ROOT/core/graph/graph.sh"

# repair_create_node GRAPH_FILE FAILED_NODE_ID REASON
# Appends a repair node that depends on FAILED_NODE_ID.
# The repair node will be run by the loop as a normal node.
repair_create_node() {
	local graph="$1"
	local failed_id="$2"
	local reason="${3:-unknown failure}"

	local repair_id="repair_${failed_id}_$(date +%s)"
	local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

	local node_json
	node_json="$(jq -n \
		--arg id         "$repair_id" \
		--arg failed_id  "$failed_id" \
		--arg reason     "$reason" \
		--arg ts         "$ts" \
		'{
			id:         $id,
			type:       "repair",
			actor:      "system",
			symbol:     "⚠︎",
			action:     "agent.ask_brain",
			depends_on: [$failed_id],
			status:     "pending",
			created_at: $ts,
			input: {
				reason:      $reason,
				failed_node: $failed_id
			}
		}'
	)"

	graph_add_node "$graph" "$node_json"
	brand_warn "repair node created: $repair_id (reason: $reason)"
	printf '%s\n' "$repair_id"
}

# repair_node_count GRAPH_FILE
# Return the number of repair nodes in the graph.
repair_node_count() {
	local graph="${1:-}"
	[[ -f "$graph" ]] || return 0
	jq '[.nodes[] | select(.type == "repair")] | length' "$graph"
}
