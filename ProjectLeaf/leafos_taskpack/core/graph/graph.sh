#!/usr/bin/env bash
# core/graph/graph.sh
# Graph CRUD helpers. All reads/writes go through jq.
# Requires: jq 1.6+
# Graph file format: runs/latest/agent.graph.json

set -uo pipefail

_GRAPH_ROOT="${_GRAPH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_GRAPH_ROOT/core/brand/brand.sh"

LEAF_GRAPH_VERSION="0.3.0"
LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_GRAPH_ROOT/runs}"
LEAF_GRAPH_LATEST="${LEAF_GRAPH_LATEST:-$LEAF_RUNS_DIR/latest/agent.graph.json}"

_graph_require_jq() {
	command -v jq &>/dev/null || {
		brand_die "jq is required for graph operations. Install: https://jqlang.github.io/jq/"
	}
}

_graph_require_file() {
	local f="${1:-$LEAF_GRAPH_LATEST}"
	[[ -f "$f" ]] || brand_die "graph file not found: $f"
	_graph_require_jq
}

# graph_init GOAL [GRAPH_FILE]
# Write a fresh empty graph to file.
graph_init() {
	local goal="$1"
	local file="${2:-$LEAF_GRAPH_LATEST}"
	_graph_require_jq
	mkdir -p "$(dirname "$file")"
	jq -n \
		--arg ver  "$LEAF_GRAPH_VERSION" \
		--arg goal "$goal" \
		--arg ts   "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		'{
			leafos_graph_version: $ver,
			goal: $goal,
			created_at: $ts,
			nodes: [],
			completion_gate: {
				required_files: [],
				required_commands: [],
				forbidden_paths: [".git/","$HOME/","/etc/","/usr/"]
			}
		}' > "$file"
	printf '%s\n' "$file"
}

# graph_add_node GRAPH_FILE NODE_JSON
# Append a node object (as JSON string) to the nodes array.
graph_add_node() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	local node_json="$2"
	_graph_require_file "$file"
	local tmp; tmp="$(mktemp)"
	jq --argjson node "$node_json" '.nodes += [$node]' "$file" > "$tmp"
	mv "$tmp" "$file"
}

# graph_node_status GRAPH_FILE NODE_ID
# Print the status string of a named node.
graph_node_status() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	local id="$2"
	_graph_require_file "$file"
	jq -r --arg id "$id" '.nodes[] | select(.id == $id) | .status // "unknown"' "$file"
}

# graph_set_status GRAPH_FILE NODE_ID STATUS
graph_set_status() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	local id="$2"
	local status="$3"
	_graph_require_file "$file"
	local tmp; tmp="$(mktemp)"
	jq --arg id "$id" --arg st "$status" \
		'(.nodes[] | select(.id == $id)).status = $st' "$file" > "$tmp"
	mv "$tmp" "$file"
}

# graph_next_ready NODE_FILE
# Print the id of the first node where status==pending and all depends_on are done.
graph_next_ready() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	_graph_require_file "$file"
	jq -r '
		.nodes as $all |
		$all[]
		| select(.status == "pending")
		| . as $node
		| (
			($node.depends_on // [])
			| all(. as $dep | ($all[] | select(.id == $dep) | .status) == "done")
		  )
		| if . then $node.id else empty end
	' "$file" | head -1
}

# graph_has_pending GRAPH_FILE  →  exit 0 if pending nodes remain, 1 otherwise
graph_has_pending() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	_graph_require_file "$file"
	local count
	count="$(jq '[.nodes[] | select(.status == "pending")] | length' "$file")"
	[[ "$count" -gt 0 ]]
}

# graph_summary GRAPH_FILE  →  print counts per status
graph_summary() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	_graph_require_file "$file"
	brand_header "Graph summary: $(basename "$(dirname "$file")")/$(basename "$file")"
	brand_kv "goal"    "$(jq -r '.goal' "$file")"
	brand_kv "version" "$(jq -r '.leafos_graph_version' "$file")"
	printf '\n'
	jq -r '
		[.nodes[] | .status] | group_by(.)[] |
		"  \(length)  \(.[0])"
	' "$file"
	printf '\n'
}

# graph_print GRAPH_FILE  →  pretty-print node table with symbols
graph_print() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	_graph_require_file "$file"
	local goal; goal="$(jq -r '.goal' "$file")"
	brand_header "❦ graph — $goal"
	printf '\n'
	jq -r '
		.nodes[] |
		[
			(if   .status == "done"    then "⚝ "
			 elif .status == "running" then "⋆ "
			 elif .status == "failed"  then "⚠︎ "
			 elif .status == "skipped" then "· "
			 else                           "❦ " end),
			(.symbol // "  "),
			"  ",
			(.id | . + (" " * (28 - length)) | .[0:28]),
			"  ",
			(.type | . + (" " * (14 - length)) | .[0:14]),
			"  ",
			.status
		] | add
	' "$file"
	printf '\n'
	graph_queue_print "$file"
}

# graph_queue_print GRAPH_FILE
# Print pending and active work with runtime-inferred model metadata.
# Node-supplied queue metadata takes precedence so schedulers can enrich rows
# without changing the graph execution contract.
graph_queue_print() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	_graph_require_file "$file"

	brand_header "*Que* — active task queue"
	printf '  %-30s  %6s  %-24s  %-12s  %-9s  %s\n' \
		'TASK' 'WEIGHT' 'INFERRED MODEL' 'QUANTIZATION' 'STATUS' 'DATE'
	printf '  %-30s  %6s  %-24s  %-12s  %-9s  %s\n' \
		'------------------------------' '------' '------------------------' '------------' '---------' '--------------------'

	local rows=0
	while IFS=$'\t' read -r task weight model quant status queued_at; do
		[[ -n "$task" ]] || continue
		printf '  %-30.30s  %6.2f  %-24.24s  %-12.12s  %-9.9s  %s\n' \
			"$task" "$weight" "$model" "$quant" "$status" "$queued_at"
		rows=$(( rows + 1 ))
	done < <(
		jq -r '
			.runtime // {} as $runtime |
			.created_at // "-" as $graph_created_at |
			def inferred_model:
				.inferred_model //
				(if .actor == "coder" then $runtime.coder_model.key
				 elif .actor == "brain" then $runtime.main_model.key
				 else $runtime.scheduler_model.key end) //
				.actor // "unassigned";
			def inferred_quantization:
				.quantization //
				(if .actor == "coder" then
					(($runtime.coder_model.tiers[]? | select(.name == $runtime.coding_choice.tier) | .quant) //
					 $runtime.coder_model.default_quant)
				 elif .actor == "brain" then $runtime.main_model.quant
				 else $runtime.scheduler_model.quant end) // "-";
			.nodes[] |
			select(.status == "pending" or .status == "running") |
			[
				(.input.task // .input.target // .id | tostring),
				(.weight // 1 | tonumber),
				(inferred_model | tostring),
				(inferred_quantization | tostring),
				(.status // "unknown"),
				(.queued_at // .created_at // $graph_created_at // "-")
			] | @tsv
		' "$file"
	)

	if [[ "$rows" -eq 0 ]]; then
		printf '  (no pending or running tasks)\n'
	fi
	printf '\n'
}

# graph_set_gate GRAPH_FILE REQUIRED_FILES_JSON REQUIRED_CMDS_JSON
graph_set_gate() {
	local file="${1:-$LEAF_GRAPH_LATEST}"
	local req_files="$2"
	local req_cmds="$3"
	_graph_require_file "$file"
	local tmp; tmp="$(mktemp)"
	jq --argjson rf "$req_files" --argjson rc "$req_cmds" \
		'.completion_gate.required_files = $rf |
		 .completion_gate.required_commands = $rc' \
		"$file" > "$tmp"
	mv "$tmp" "$file"
}
