#!/usr/bin/env bash
# core/agent/actions.sh
# Embedded agentic action dispatcher.
# Implements the 11 action types defined in the 0.4.0 spec.
# Each action is a bounded, self-contained callable unit.
#
# Symbols:
#   ❦  node selected
#   ⋆  model action generated
#   𓂃  shell/write action performed
#   ⚠︎  warning/error
#   ⚝  verified

set -uo pipefail

_ACTIONS_ROOT="${_ACTIONS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_ACTIONS_ROOT/core/brand/brand.sh"
source "$_ACTIONS_ROOT/core/agent/wait.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_ACTIONS_ROOT/runs}"
LEAF_RUN_DIR="${LEAF_RUN_DIR:-$LEAF_RUNS_DIR/latest}"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_action_log() {
	local node_id="$1" action="$2" result="$3"
	local ts; ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	local stream="system"
	case "$action" in
		agent.ask_brain) stream="brain" ;;
		agent.ask_coder) stream="coder" ;;
		agent.dual_think) stream="dual" ;;
		patch.*|shell.*|verify.*) stream="execution" ;;
		wait.*) stream="wait" ;;
		report.*) stream="report" ;;
	esac
	mkdir -p "$LEAF_RUN_DIR"
	jq -n -c \
		--arg ts "$ts" \
		--arg node "$node_id" \
		--arg action "$action" \
		--arg stream "$stream" \
		--arg result "$result" \
		'{ts:$ts,node:$node,action:$action,stream:$stream,result:$result}' \
		>> "$LEAF_RUN_DIR/actions.jsonl"
}

_action_result_write() {
	local node_id="$1" action="$2" status="$3" exit_code="$4" started_at="$5" finished_at="$6"
	local safe_node; safe_node="$(printf '%s' "$node_id" | tr -c 'A-Za-z0-9_.-' '_')"
	local result_dir="$LEAF_RUN_DIR/action-results"
	local result_file="$result_dir/$safe_node.json"
	local tmp_file="$result_file.tmp.$$"
	mkdir -p "$result_dir"
	jq -n \
		--arg node "$node_id" \
		--arg action "$action" \
		--arg status "$status" \
		--argjson exit_code "$exit_code" \
		--arg started_at "$started_at" \
		--arg finished_at "$finished_at" \
		--arg stream "$(case "$action" in agent.ask_brain) printf brain ;; agent.ask_coder) printf coder ;; agent.dual_think) printf dual ;; *) printf system ;; esac)" \
		'{node: $node, action: $action, stream: $stream, status: $status, exit_code: $exit_code, started_at: $started_at, finished_at: $finished_at, artifacts: []}' \
		> "$tmp_file" && mv "$tmp_file" "$result_file"
	if [[ "$action" == "agent.dual_think" ]]; then
		local dual_dir="$LEAF_RUN_DIR/dual-thinking/$(printf '%s' "$node_id" | tr -c 'A-Za-z0-9_.-' '_')"
		local artifacts_json='[]' candidate
		for candidate in "$dual_dir/brain.graph.json" "$dual_dir/coder.handoff.md" "$dual_dir/dual-thinking.json" "$dual_dir/coder/patch.diff" "$dual_dir/coder/validation.log"; do
			if [[ -f "$candidate" ]]; then
				artifacts_json="$(jq --arg path "$candidate" '. + [$path]' <<< "$artifacts_json")"
			fi
		done
		jq --argjson artifacts "$artifacts_json" '.artifacts = $artifacts' "$result_file" > "$tmp_file" && mv "$tmp_file" "$result_file"
	elif [[ "$action" == "agent.ask_coder" && -s "$LEAF_RUN_DIR/coder.patch" ]]; then
		jq --arg artifact "$LEAF_RUN_DIR/coder.patch" '.artifacts = [$artifact]' "$result_file" > "$tmp_file" && mv "$tmp_file" "$result_file"
	fi
}

_action_header() {
	local symbol="${1:-⋆}" label="$2"
	printf '\n  %s%s%s  %s%s%s\n' \
		"$C_CYAN_B" "$symbol" "$C_RESET" \
		"$C_BOLD"   "$label"  "$C_RESET"
}

# ---------------------------------------------------------------------------
# 1. agent.ask_brain
# Purpose: Convert task intent into graph nodes or repair instructions.
# Output:  runs/latest/brain.taskpack.json
# In 0.3.0 this is fulfilled by brain.sh directly; this action type is a
# re-entry point for mid-loop re-planning calls.
# ---------------------------------------------------------------------------
action_ask_brain() {
	local node_id="$1" input_json="$2"
	local task_file; task_file="$(jq -r '.task_file // ""' <<< "$input_json")"
	local outfile="$LEAF_RUN_DIR/brain.taskpack.json"

	_action_header "⋆" "agent.ask_brain  node=$node_id"
	brand_kv "input" "${task_file:-<stdin>}"
	brand_kv "output" "$outfile"

	if [[ -n "$task_file" && -f "$task_file" ]]; then
		# Delegate to brain model
		source "$_ACTIONS_ROOT/core/model/brain.sh"
		brain_generate_graph "$task_file" "$outfile"
	else
		brand_warn "agent.ask_brain: no task_file in input; skipping"
		return 1
	fi

	_action_log "$node_id" "agent.ask_brain" "ok"
}

# ---------------------------------------------------------------------------
# 2. agent.ask_coder
# Purpose: Generate a bounded unified diff patch.
# Output:  runs/latest/coder.patch
# ---------------------------------------------------------------------------
action_ask_coder() {
	local node_id="$1" input_json="$2"
	local safe_node; safe_node="$(printf '%s' "$node_id" | tr -c 'A-Za-z0-9_.-' '_')"
	local coder_run_dir="$LEAF_RUN_DIR/coder/$safe_node"
	local outfile="$coder_run_dir/patch.diff"
	local task_file; task_file="$(jq -r '.task_file // ""' <<< "$input_json")"

	_action_header "⋆" "agent.ask_coder  node=$node_id"
	brand_kv "stream" "coder"
	brand_kv "output" "$outfile"

	source "$_ACTIONS_ROOT/core/model/coder.sh"
	mkdir -p "$coder_run_dir"

	local rc
	if [[ -n "$task_file" ]]; then
		coder_generate_patch "$task_file" "$coder_run_dir"
		rc=$?
	else
		coder_generate_patch_from_node "$node_id" "$input_json" "$coder_run_dir"
		rc=$?
	fi

	if [[ "$rc" -ne 0 || ! -s "$outfile" ]]; then
		brand_warn "agent.ask_coder: patch generation or validation failed."
		_action_log "$node_id" "agent.ask_coder" "fail:patch_gate"
		return 1
	fi

	cp "$outfile" "$LEAF_RUN_DIR/coder.patch"
	brand_ok "coder patch validated; application remains a separate action."
	brand_kv "validated_patch" "$outfile"

	_action_log "$node_id" "agent.ask_coder" "ok"
	return 0
}

# ---------------------------------------------------------------------------
# 3. agent.dual_think
# Purpose: Run the explicit planner -> coder handoff.
# Outputs: dual-thinking.json, brain.graph.json, coder/<node>/patch.diff.
# The action records structured decisions and artifacts, never private model
# chain-of-thought, and never applies a patch implicitly.
# ---------------------------------------------------------------------------
action_dual_think() {
	local node_id="$1" input_json="$2"
	local task_file; task_file="$(jq -r '.task_file // ""' <<< "$input_json")"
	local safe_node; safe_node="$(printf '%s' "$node_id" | tr -c 'A-Za-z0-9_.-' '_')"
	local stream_dir="$LEAF_RUN_DIR/dual-thinking/$safe_node"
	local graph_file="$stream_dir/brain.graph.json"
	local handoff_file="$stream_dir/coder.handoff.md"
	local state_file="$stream_dir/dual-thinking.json"

	_action_header "⋆" "agent.dual_think  node=$node_id"
	brand_kv "stream" "brain -> coder"
	brand_kv "task" "${task_file:-<missing>}"

	if [[ -z "$task_file" || ! -f "$task_file" ]]; then
		brand_warn "agent.dual_think: task_file is required and must exist."
		_action_log "$node_id" "agent.dual_think" "fail:no_task_file"
		return 1
	fi

	mkdir -p "$stream_dir"
	jq -n \
		--arg node "$node_id" \
		--arg task "$task_file" \
		'{node:$node, task_file:$task, planner:{status:"pending"}, coder:{status:"pending"}, patch_application:"not_requested"}' \
		> "$state_file"

	source "$_ACTIONS_ROOT/core/model/brain.sh"
	if ! brain_generate_graph "$task_file" "$graph_file" >/dev/null; then
		jq '.planner.status = "failed" | .failure = "planner"' "$state_file" > "$state_file.tmp" && mv "$state_file.tmp" "$state_file"
		_action_log "$node_id" "agent.dual_think" "fail:planner"
		return 1
	fi

	jq --arg graph "$graph_file" '.planner = {status:"completed", artifact:$graph}' "$state_file" > "$state_file.tmp" && mv "$state_file.tmp" "$state_file"

	{
		printf '# Dual thinking coder handoff\n\n'
		printf 'The planner stream produced the structured graph below. Treat it as bounded implementation context.\n\n'
		printf '## Original task\n\n'
		cat "$task_file"
		printf '\n\n## Planner graph\n\n```json\n'
		cat "$graph_file"
		printf '\n```\n\n## Coder contract\n\n'
		printf '%s\n' '- Return a unified diff only.' '- Stay within the task scope.' '- Do not apply changes.' '- Local validation must pass before success.'
	} > "$handoff_file"

	source "$_ACTIONS_ROOT/core/model/coder.sh"
	local coder_dir="$stream_dir/coder"
	if ! coder_generate_patch "$handoff_file" "$coder_dir" >/dev/null; then
		jq --arg handoff "$handoff_file" '.coder = {status:"failed", handoff:$handoff} | .failure = "coder"' "$state_file" > "$state_file.tmp" && mv "$state_file.tmp" "$state_file"
		_action_log "$node_id" "agent.dual_think" "fail:coder"
		return 1
	fi

	jq --arg handoff "$handoff_file" --arg patch "$coder_dir/patch.diff" \
		'.coder = {status:"completed", handoff:$handoff, validated_patch:$patch} | .status = "validated"' \
		"$state_file" > "$state_file.tmp" && mv "$state_file.tmp" "$state_file"
	cp "$coder_dir/patch.diff" "$LEAF_RUN_DIR/coder.patch"
	brand_ok "dual stream completed: planner graph and coder patch validated."
	brand_kv "state" "$state_file"
	brand_kv "apply" "separate action only"
	_action_log "$node_id" "agent.dual_think" "ok"
}

# ---------------------------------------------------------------------------
# 3. fs.inspect
# Purpose: Read files, list layout, gather context.
# ---------------------------------------------------------------------------
action_fs_inspect() {
	local node_id="$1" input_json="$2"
	local target; target="$(jq -r '.target // "."' <<< "$input_json")"

	_action_header "𓂃" "fs.inspect  node=$node_id  target=$target"
	if [[ -d "$target" ]]; then
		find "$target" -maxdepth 3 -not -path '*/.git/*' \
			| sort | head -60 | while read -r p; do
				printf '  %s%s%s\n' "$C_DIM" "$p" "$C_RESET"
			  done
	elif [[ -f "$target" ]]; then
		head -20 "$target" | while read -r line; do
			printf '  %s\n' "$line"
		done
	else
		brand_warn "fs.inspect: target not found: $target"
		return 1
	fi

	_action_log "$node_id" "fs.inspect" "ok"
}

# ---------------------------------------------------------------------------
# 4. fs.require_file
# Purpose: Assert a file exists; fail node if missing.
# ---------------------------------------------------------------------------
action_fs_require_file() {
	local node_id="$1" input_json="$2"
	local target; target="$(jq -r '.target // ""' <<< "$input_json")"

	_action_header "𓂃" "fs.require_file  node=$node_id"
	brand_kv "target" "$target"

	if [[ -s "$target" ]]; then
		brand_ok "$target exists and is non-empty."
		_action_log "$node_id" "fs.require_file" "ok"
		return 0
	else
		brand_warn "fs.require_file: missing or empty: $target"
		_action_log "$node_id" "fs.require_file" "fail:missing"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# 5. patch.validate
# ---------------------------------------------------------------------------
action_patch_validate() {
	local node_id="$1" input_json="$2"
	local patch; patch="$(jq -r '.patch_file // ""' <<< "$input_json")"
	[[ -z "$patch" ]] && patch="$LEAF_RUN_DIR/coder.patch"

	_action_header "𓂃" "patch.validate  node=$node_id"
	brand_kv "patch" "$patch"

	if [[ ! -f "$patch" ]]; then
		brand_warn "patch.validate: patch file not found: $patch"
		_action_log "$node_id" "patch.validate" "fail:not_found"
		return 1
	fi

	if git apply --check "$patch" 2>&1; then
		brand_ok "patch validates cleanly."
		_action_log "$node_id" "patch.validate" "ok"
		return 0
	else
		brand_warn "patch.validate: git apply --check failed."
		_action_log "$node_id" "patch.validate" "fail:check"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# 6. patch.apply
# ---------------------------------------------------------------------------
action_patch_apply() {
	local node_id="$1" input_json="$2"
	local patch; patch="$(jq -r '.patch_file // ""' <<< "$input_json")"
	[[ -z "$patch" ]] && patch="$LEAF_RUN_DIR/coder.patch"

	_action_header "𓂃" "patch.apply  node=$node_id"
	brand_kv "patch" "$patch"

	if git apply "$patch" 2>&1; then
		brand_ok "patch applied."
		_action_log "$node_id" "patch.apply" "ok"
	else
		brand_warn "patch.apply: apply failed."
		_action_log "$node_id" "patch.apply" "fail:apply"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# 7. shell.run
# Purpose: Run a bounded shell command. No sudo. No pipe-to-sh.
# ---------------------------------------------------------------------------
action_shell_run() {
	local node_id="$1" input_json="$2"
	local cmd; cmd="$(jq -r '.command // ""' <<< "$input_json")"
	local workdir; workdir="$(jq -r '.workdir // ""' <<< "$input_json")"

	_action_header "𓂃" "shell.run  node=$node_id"
	brand_kv "command" "$cmd"

	if [[ -z "$cmd" ]]; then
		brand_warn "shell.run: no command specified."
		_action_log "$node_id" "shell.run" "fail:no_cmd"
		return 1
	fi

	# Safety check: block destructive patterns
	if printf '%s' "$cmd" | grep -qE '(rm[[:space:]]+-rf|mkfs|dd[[:space:]]+if=|shutdown|reboot|curl.*\|.*sh|wget.*\|.*sh|sudo)'; then
		brand_warn "shell.run: blocked — destructive or unsafe pattern detected."
		_action_log "$node_id" "shell.run" "fail:blocked"
		return 1
	fi

	if [[ -n "$workdir" ]]; then
		(cd "$workdir" && bash -c "$cmd")
	else
		bash -c "$cmd"
	fi
	local rc=$?

	if [[ $rc -eq 0 ]]; then
		brand_ok "command succeeded."
		_action_log "$node_id" "shell.run" "ok"
	else
		brand_warn "command failed (exit $rc)."
		_action_log "$node_id" "shell.run" "fail:exit_$rc"
		return $rc
	fi
}

# ---------------------------------------------------------------------------
# 8. wait.file  — thin wrapper; real logic is in wait.sh
# ---------------------------------------------------------------------------
action_wait_file() {
	local node_id="$1" input_json="$2"
	local target;   target="$(jq -r   '.target // ""'          <<< "$input_json")"
	local interval; interval="$(jq -r '.interval_seconds // 1' <<< "$input_json")"
	local maxatt;   maxatt="$(jq -r   '.max_attempts // 60'     <<< "$input_json")"

	_action_header "❑" "wait.file  node=$node_id"
	brand_kv "target"   "$target"
	brand_kv "interval" "${interval}s"
	brand_kv "max"      "$maxatt attempts"

	leaf_wait_file "$target" "$interval" "$maxatt"
	local rc=$?
	_action_log "$node_id" "wait.file" "$(( rc == 0 ? 'ok' : 'timeout' ))"
	return $rc
}

# ---------------------------------------------------------------------------
# 9. wait.command_success
# ---------------------------------------------------------------------------
action_wait_command_success() {
	local node_id="$1" input_json="$2"
	local target;   target="$(jq -r   '.target // ""'          <<< "$input_json")"
	local interval; interval="$(jq -r '.interval_seconds // 2' <<< "$input_json")"
	local maxatt;   maxatt="$(jq -r   '.max_attempts // 30'     <<< "$input_json")"

	_action_header "❑" "wait.command_success  node=$node_id"
	leaf_wait_command "$target" "$interval" "$maxatt"
	local rc=$?
	_action_log "$node_id" "wait.command_success" "$(( rc == 0 ? 'ok' : 'timeout' ))"
	return $rc
}

# ---------------------------------------------------------------------------
# 10. verify.run
# ---------------------------------------------------------------------------
action_verify_run() {
	local node_id="$1" input_json="$2"
	local cmd; cmd="$(jq -r '.command // ""' <<< "$input_json")"

	_action_header "⚝" "verify.run  node=$node_id"
	brand_kv "command" "$cmd"

	if bash -c "$cmd"; then
		brand_ok "verify passed."
		_action_log "$node_id" "verify.run" "ok"
		return 0
	else
		brand_warn "verify failed."
		_action_log "$node_id" "verify.run" "fail"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# 11. report.append
# ---------------------------------------------------------------------------
action_report_append() {
	local node_id="$1" input_json="$2"
	local message; message="$(jq -r '.message // ""' <<< "$input_json")"
	local outfile="${LEAF_RUN_DIR}/report.md"

	_action_header "⎙" "report.append  node=$node_id"
	mkdir -p "$LEAF_RUN_DIR"
	printf '\n## %s\n\n%s\n' "$node_id" "$message" >> "$outfile"
	brand_ok "appended to $outfile"
	_action_log "$node_id" "report.append" "ok"
}

# ---------------------------------------------------------------------------
# 12. repair.create_node  [see also repair.sh]
# ---------------------------------------------------------------------------
action_repair_create_node() {
	local node_id="$1" input_json="$2"
	local reason; reason="$(jq -r '.reason // "unknown failure"' <<< "$input_json")"
	local graph;  graph="$(jq -r '.graph_file // ""'             <<< "$input_json")"
	[[ -z "$graph" ]] && graph="$LEAF_RUN_DIR/agent.graph.json"

	_action_header "⚠︎" "repair.create_node  node=$node_id"
	brand_kv "reason" "$reason"

	source "$_ACTIONS_ROOT/core/agent/repair.sh"
	repair_create_node "$graph" "$node_id" "$reason"
	_action_log "$node_id" "repair.create_node" "ok"
}

# ---------------------------------------------------------------------------
# Main dispatcher: agent_run_action ACTION NODE_ID INPUT_JSON
# ---------------------------------------------------------------------------
agent_run_action() {
	local action="$1"
	local node_id="$2"
	local input_json="${3:-{}}"
	local started_at; started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	local rc=0

	case "$action" in
		agent.ask_brain)       action_ask_brain           "$node_id" "$input_json" || rc=$? ;;
		agent.ask_coder)       action_ask_coder           "$node_id" "$input_json" || rc=$? ;;
		agent.dual_think)      action_dual_think           "$node_id" "$input_json" || rc=$? ;;
		fs.inspect)            action_fs_inspect          "$node_id" "$input_json" || rc=$? ;;
		fs.require_file)       action_fs_require_file     "$node_id" "$input_json" || rc=$? ;;
		patch.validate)        action_patch_validate      "$node_id" "$input_json" || rc=$? ;;
		patch.apply)           action_patch_apply         "$node_id" "$input_json" || rc=$? ;;
		shell.run)             action_shell_run           "$node_id" "$input_json" || rc=$? ;;
		wait.file)             action_wait_file           "$node_id" "$input_json" || rc=$? ;;
		wait.command_success)  action_wait_command_success "$node_id" "$input_json" || rc=$? ;;
		verify.run)            action_verify_run          "$node_id" "$input_json" || rc=$? ;;
		report.append)         action_report_append       "$node_id" "$input_json" || rc=$? ;;
		repair.create_node)    action_repair_create_node  "$node_id" "$input_json" || rc=$? ;;
		*)
			brand_warn "unknown action type: $action (node $node_id)"
			rc=1
			;;
	esac

	local finished_at; finished_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	local status='failed'
	[[ "$rc" -eq 0 ]] && status='passed'
	_action_result_write "$node_id" "$action" "$status" "$rc" "$started_at" "$finished_at"
	return "$rc"
}
