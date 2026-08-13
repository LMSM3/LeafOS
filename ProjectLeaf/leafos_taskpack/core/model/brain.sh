#!/usr/bin/env bash
# core/model/brain.sh
# Brain model: converts a task file into agent.graph.json.
#
# LEAF_PROVIDER_MODE=llamacpp|ollama|openai|... routes to a live model.
# LEAF_PROVIDER_MODE=off fails closed because graph generation requires a model.
# The deterministic parser is retained only as an explicitly gated test fixture.
#
# Output format: runs/latest/agent.graph.json (0.3.0 schema)

set -uo pipefail

_BRAIN_ROOT="${_BRAIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_BRAIN_ROOT/core/brand/brand.sh"
source "$_BRAIN_ROOT/core/graph/graph.sh"
source "$_BRAIN_ROOT/core/providers/providers.sh"
source "$_BRAIN_ROOT/core/graph/graph_validate.sh"
source "$_BRAIN_ROOT/core/agent/manifest.sh"
source "$_BRAIN_ROOT/core/runtime/runtime.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_BRAIN_ROOT/runs}"

# ---------------------------------------------------------------------------
# brain_generate_graph TASK_FILE [GRAPH_FILE]
# Parse the task markdown and produce a graph JSON file.
# Returns the path to the graph file on success.
# ---------------------------------------------------------------------------
brain_generate_graph() {
	local task_file="$1"
	local graph_file="${2:-$LEAF_RUNS_DIR/latest/agent.graph.json}"

	[[ -f "$task_file" ]] || {
		brand_die "brain: task file not found: $task_file"
	}

	_graph_require_jq

	local provider="${LEAF_BRAIN_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}"
	if [[ "$provider" == "off" ]]; then
		brand_warn "brain: provider is disabled; configure LEAF_BRAIN_PROVIDER or LEAF_PROVIDER_MODE"
		return 2
	fi
	if [[ "$provider" == "mock" && "${LEAF_ENABLE_TEST_MOCK_PROVIDER:-0}" != "1" ]]; then
		brand_warn "brain: mock provider is test-only (set LEAF_ENABLE_TEST_MOCK_PROVIDER=1 in a test process)"
		return 2
	fi

	# -- Live provider path ---------------------------------------------------
	# Contract v1: call leaf_provider_call DIRECTLY (never in a subshell).
	# Model text is in LEAF_PROVIDER_TEXT_FILE; we read the file, never the var.
	if [[ "$provider" != "mock" ]]; then
		local _bp_run_dir; _bp_run_dir="$(manifest_run_dir_new)"
		leaf_provider_call "$task_file" "$_bp_run_dir" "$provider"
		if [[ "${LEAF_PROVIDER_OK:-0}" == "1" && -s "${LEAF_PROVIDER_TEXT_FILE:-}" ]]; then
			manifest_write_env "$_bp_run_dir"
			manifest_write_clean "$_bp_run_dir"
			local plan_text; plan_text="$(cat "$LEAF_PROVIDER_TEXT_FILE")"
			if _brain_plan_to_graph "$plan_text" "$task_file" "$graph_file"; then
				if graph_validate "$graph_file" "$_BRAIN_ROOT" >&2; then
					manifest_write "$_bp_run_dir" "completed" "graph=${graph_file}"
					manifest_symlink_latest "$_bp_run_dir"
					printf '%s\n' "$graph_file"
					return 0
				fi
				LEAF_PROVIDER_ERROR="graph_validation_failed"
			fi
		fi
		brand_warn "brain: live provider failed (${LEAF_PROVIDER_ERROR:-invalid_provider_plan})"
		manifest_write "$_bp_run_dir" "failed" "error=${LEAF_PROVIDER_ERROR:-unknown}"
		return 2
	fi

	# -- Explicit test-fixture parser --------------------------------------------
	# -- Extract task metadata from markdown ------------------------------------
	local title scope
	title="$(grep -m1 '^# ' "$task_file" 2>/dev/null | sed 's/^# //')"
	[[ -n "$title" ]] || title="$(basename "$task_file" .md)"

	scope="$(awk '/^## Scope/{found=1; next} found && /^##/{exit} found{print}' "$task_file" \
			  | head -5 | tr '\n' ' ' | xargs)"
	[[ -n "$scope" ]] || scope="general task"

	# -- Extract steps from markdown -----------------------------------------
	# Look for lines like "1. verb target" or "- verb target"
	local step_lines
	mapfile -t step_lines < <(
		grep -E '^\s*[-*]|\s*[0-9]+\.' "$task_file" \
		| sed 's/^\s*[-*0-9.]\+\s*//' \
		| grep -v '^$' \
		| head -8
	)

	# Build canonical node list from discovered steps + fixed scaffold
	local goal="${title}: ${scope}"
	local run_dir; run_dir="$(dirname "$graph_file")"
	mkdir -p "$run_dir"

	# Initialise graph
	graph_init "$goal" "$graph_file" >/dev/null
	_brain_attach_runtime_metadata "$graph_file"

	# -- Fixed structural nodes (always present) ------------------------------
	graph_add_node "$graph_file" "$(jq -n '{
		id: "brain_inspect",
		type: "inspect",
		actor: "brain",
		symbol: "⋆",
		action: "fs.inspect",
		depends_on: [],
		status: "pending",
		input: { target: "." }
	}')"

	# -- Task-derived step nodes (max 6) -------------------------------------
	local prev_id="brain_inspect"
	local i=0
	local step_id step_label
	for step_label in "${step_lines[@]}"; do
		step_id="step_$(printf '%02d' $((i+1)))_$(printf '%s' "$step_label" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_' | cut -c1-24)"
		graph_add_node "$graph_file" "$(jq -n \
			--arg id       "$step_id" \
			--arg label    "$step_label" \
			--arg prev     "$prev_id" \
			'{
				id:         $id,
				type:       "write",
				actor:      "coder",
				symbol:     "⋆",
				action:     "agent.ask_coder",
				depends_on: [$prev],
				status:     "pending",
				input:      { task: $label, output_format: "unified_diff" }
			}'
		)"
		prev_id="$step_id"
		i=$(( i + 1 ))
		(( i >= 6 )) && break
	done

	# If no steps were extracted, add a single implement node
	if [[ ${#step_lines[@]} -eq 0 ]]; then
		graph_add_node "$graph_file" "$(jq -n \
			--arg prev "$prev_id" \
			--arg task "$title" \
			'{
				id:         "implement",
				type:       "write",
				actor:      "coder",
				symbol:     "⋆",
				action:     "agent.ask_coder",
				depends_on: [$prev],
				status:     "pending",
				input:      { task: $task, output_format: "unified_diff" }
			}'
		)"
		prev_id="implement"
	fi

	# -- Fixed tail nodes ----------------------------------------------------
	graph_add_node "$graph_file" "$(jq -n \
		--arg prev "$prev_id" \
		'{
			id:         "verify",
			type:       "verify",
			actor:      "system",
			symbol:     "⚝",
			action:     "verify.run",
			depends_on: [$prev],
			status:     "pending",
			input:      { command: "bash tests/smoke.sh 2>/dev/null || true" }
		}'
	)"

	graph_add_node "$graph_file" '{"id":"completion_gate","type":"gate","actor":"system","symbol":"ꕤ","action":"shell.run","depends_on":["verify"],"status":"pending","input":{"command":"echo gate_reached"}}'

	# -- Set completion gate criteria ----------------------------------------
	graph_set_gate "$graph_file" \
		'["README.md","tests/smoke.sh"]' \
		'["bash -n bin/leafctl"]'
	_brain_attach_queue_metadata "$graph_file"

	printf '%s\n' "$graph_file"
}

# ---------------------------------------------------------------------------
# brain_inspect_graph GRAPH_FILE
# Pretty-print a graph file.
# ---------------------------------------------------------------------------
brain_inspect_graph() {
	local graph="${1:-$LEAF_RUNS_DIR/latest/agent.graph.json}"
	graph_print "$graph"
graph_summary "$graph"
}

_brain_attach_runtime_metadata() {
	local graph_file="$1"
	command -v jq &>/dev/null || return 0
	declare -F leaf_runtime_select >/dev/null || return 0
	[[ -f "$graph_file" ]] || return 0

	local selection tmp
	selection="$(leaf_runtime_select --json 2>/dev/null)" || return 0
	tmp="$(mktemp)"
	if jq --argjson runtime "$selection" '.runtime = $runtime.selection' "$graph_file" > "$tmp"; then
		mv "$tmp" "$graph_file"
	else
		rm -f "$tmp"
	fi
}

_brain_attach_queue_metadata() {
	local graph_file="$1"
	command -v jq &>/dev/null || return 0
	[[ -f "$graph_file" ]] || return 0

	local queued_at tmp
	queued_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	tmp="$(mktemp)"
	if jq --arg queued_at "$queued_at" '
		.runtime // {} as $runtime |
		.nodes |= map(
			. as $node |
			(if ($node.actor // "system") == "coder" then
				($runtime.coder_model.key // "coder")
			 elif ($node.actor // "system") == "brain" then
				($runtime.main_model.key // "brain")
			 else
				($runtime.scheduler_model.key // $runtime.main_model.key // "system")
			 end) as $model |
			(if ($node.actor // "system") == "coder" then
				(($runtime.coder_model.tiers[]? | select(.name == $runtime.coding_choice.tier) | .quant) //
				 $runtime.coder_model.default_quant // "-")
			 elif ($node.actor // "system") == "brain" then
				($runtime.main_model.quant // "-")
			 else
				($runtime.scheduler_model.quant // $runtime.main_model.quant // "-")
			 end) as $quant |
			. + {
				weight: (.weight // (if .type == "gate" then 0.5 elif .type == "verify" then 1.5 elif .actor == "coder" then 2.0 else 1.0 end)),
				inferred_model: (.inferred_model // $model),
				quantization: (.quantization // $quant),
				queued_at: (.queued_at // $queued_at)
			}
		)
	' "$graph_file" > "$tmp"; then
		mv "$tmp" "$graph_file"
	else
		rm -f "$tmp"
	fi
}

# ---------------------------------------------------------------------------
# _brain_plan_to_graph PLAN_TEXT TASK_FILE GRAPH_FILE
# Convert a LEAFOS_AGENT_PLAN bash script (from live provider) into a graph.
# Each run_step() call in the plan becomes a write-node.
# Returns 0 on success, 1 if the plan text looks invalid.
# ---------------------------------------------------------------------------
_brain_plan_to_graph() {
	local plan_text="$1" task_file="$2" graph_file="$3"

	# Require the LEAFOS_AGENT_PLAN marker
	printf '%s' "$plan_text" | grep -q 'LEAFOS_AGENT_PLAN=1' || {
		brand_warn "brain: provider output missing LEAFOS_AGENT_PLAN=1 marker"
		return 1
	}

	local title
	title="$(grep -m1 '^# ' "$task_file" 2>/dev/null | sed 's/^# //')"
	[[ -n "$title" ]] || title="$(basename "$task_file" .md)"

	local goal="${title}: generated by ${LEAF_PROVIDER_MODE}"
	local run_dir; run_dir="$(dirname "$graph_file")"
	mkdir -p "$run_dir"

	graph_init "$goal" "$graph_file" >/dev/null
	_brain_attach_runtime_metadata "$graph_file"

	# Fixed inspect node
	graph_add_node "$graph_file" "$(jq -n '{
		id: "brain_inspect", type: "inspect", actor: "brain",
		symbol: "⋆", action: "fs.inspect",
		depends_on: [], status: "pending",
		input: { target: "." }
	}')"

	# Extract run_step lines and turn each into a write-node
	local prev_id="brain_inspect" i=0 step_label step_id
	while IFS= read -r step_label; do
		[[ -z "$step_label" ]] && continue
		step_id="step_$(printf '%02d' $((i+1)))_$(printf '%s' "$step_label" | \
			tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_' | cut -c1-24)"
		graph_add_node "$graph_file" "$(jq -n \
			--arg id    "$step_id" \
			--arg label "$step_label" \
			--arg prev  "$prev_id" \
			'{ id: $id, type: "write", actor: "coder", symbol: "⋆",
			   action: "agent.ask_coder", depends_on: [$prev],
			   status: "pending",
			   input: { task: $label, output_format: "unified_diff" } }')"
		prev_id="$step_id"
		i=$(( i + 1 ))
		(( i >= 8 )) && break
	done < <(printf '%s' "$plan_text" | grep 'run_step' | \
		sed 's/^[[:space:]]*run_step[[:space:]]*//' | head -8)

	# Verify + gate
	graph_add_node "$graph_file" "$(jq -n --arg prev "$prev_id" '{
		id: "verify", type: "verify", actor: "system", symbol: "✝",
		action: "verify.run", depends_on: [$prev], status: "pending",
		input: { command: "bash tests/smoke.sh 2>/dev/null || true" }
	}')"
	graph_add_node "$graph_file" '{"id":"completion_gate","type":"gate","actor":"system","symbol":"꘤","action":"shell.run","depends_on":["verify"],"status":"pending","input":{"command":"echo gate_reached"}}'
	graph_set_gate "$graph_file" '["README.md","tests/smoke.sh"]' '["bash -n bin/leafctl"]'

	printf '%s\n' "$graph_file"
}
