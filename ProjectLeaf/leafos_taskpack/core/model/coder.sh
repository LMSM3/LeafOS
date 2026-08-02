#!/usr/bin/env bash
# core/model/coder.sh  --  Coder model (WO-007-C §7)
#
# coder_generate_patch TASK_FILE [RUN_DIR]
#   Routes to LEAF_CODER_PROVIDER, reads raw model output from
#   LEAF_PROVIDER_TEXT_FILE, validates, writes patch.diff.
#   Returns 0 on success and fails closed on provider failure.
#
# coder_generate_patch_from_node NODE_ID INPUT_JSON [RUN_DIR]
#   Convenience: builds a task file from the graph node then calls
#   coder_generate_patch.

set -uo pipefail

_CODER_ROOT="${_CODER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_CODER_ROOT/core/brand/brand.sh"
source "$_CODER_ROOT/core/providers/providers.sh"
source "$_CODER_ROOT/core/patch/validate.sh"
source "$_CODER_ROOT/core/agent/manifest.sh"
source "$_CODER_ROOT/core/runtime/runtime.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_CODER_ROOT/runs}"

# ---------------------------------------------------------------------------
# coder_generate_patch TASK_FILE [RUN_DIR]
# ---------------------------------------------------------------------------
coder_generate_patch() {
	local task_file="${1:-}"
	local run_dir="${2:-}"

	[[ -f "$task_file" ]] || { brand_warn "coder: task file not found: $task_file"; return 1; }

	# Establish or reuse run directory
	if [[ -z "$run_dir" ]]; then
		run_dir="$(manifest_run_dir_new)"
	fi
	mkdir -p "$run_dir"

	local patch_file="$run_dir/patch.diff"
	local validation_log="$run_dir/validation.log"

	brand_header "coder: generating patch"
	brand_kv "task"     "$task_file"
	brand_kv "provider" "${LEAF_CODER_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}"
	brand_kv "out"      "$run_dir"

	# Contract-v1 call: DIRECT call, never in a subshell
	leaf_provider_call "$task_file" "$run_dir" "${LEAF_CODER_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}"

	if [[ "${LEAF_PROVIDER_OK:-0}" != "1" ]]; then
		brand_warn "coder: provider failed: ${LEAF_PROVIDER_ERROR:-unknown} (${LEAF_PROVIDER_MS:-0}ms)"
		manifest_write "$run_dir" "failed" "error=${LEAF_PROVIDER_ERROR:-unknown}"
		return 2
	fi

	# Write manifest env snapshot
	manifest_write_env "$run_dir"

	# The raw model output is already at LEAF_PROVIDER_TEXT_FILE (written by adapter)
	# Copy to patch.diff atomically
	local raw="${LEAF_PROVIDER_TEXT_FILE:-}"
	[[ -s "$raw" ]] || {
		brand_warn "coder: provider returned empty response"
		manifest_write "$run_dir" "failed" "error=empty_response"
		return 1
	}

	# Atomic write: strip any accidental ANSI then move
	local tmp_patch; tmp_patch="$run_dir/patch.diff.tmp.$$"
	sed 's/\x1b\[[0-9;]*m//g' "$raw" >"$tmp_patch" && mv "$tmp_patch" "$patch_file"

	brand_kv "bytes"    "${LEAF_PROVIDER_BYTES:-0}"
	brand_kv "ms"       "${LEAF_PROVIDER_MS:-0}ms"

	# Gate: validate the patch before declaring success
	brand_say "running patch gate..."
	if patch_validate "$patch_file" "$_CODER_ROOT" >"$validation_log" 2>&1; then
		brand_ok "patch validated: $patch_file"
		manifest_write "$run_dir" "completed" "patch=${patch_file}"
		manifest_symlink_latest "$run_dir"
		printf '%s\n' "$patch_file"
		return 0
	else
		brand_warn "coder: patch did not pass validation (see $validation_log)"
		cat "$validation_log" >&2
		manifest_write "$run_dir" "failed" "error=patch_validation_failed"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# coder_generate_patch_from_node NODE_ID INPUT_JSON [RUN_DIR]
# Build a minimal task file from the coder graph node and call the pipeline.
# ---------------------------------------------------------------------------
coder_generate_patch_from_node() {
	local node_id="${1:-}"
	local input_json="${2:-{}}"
	local run_dir="${3:-}"

	[[ -n "$node_id" ]] || { brand_warn "coder_generate_patch_from_node: no node_id"; return 1; }

	local task_label
	task_label="$(printf '%s' "$input_json" | python3 -c "
import json,sys
d=json.load(sys.stdin); print(d.get('task','implement node: $node_id'))" 2>/dev/null \
		|| echo "implement node: $node_id")"

	local tmp_task; tmp_task="$(mktemp /tmp/leaf_coder_task_XXXXXX.md)"
	{
		printf '# Coder task: %s\n\n' "$node_id"
		printf '## Steps\n1. %s\n\n' "$task_label"
		printf '## Format\n- Output must be a valid unified diff.\n'
		printf '%s\n' '- Use `--- a/file` and `+++ b/file` headers.'
		printf '%s\n' '- Do not include explanatory text outside the diff.'
	} >"$tmp_task"

	coder_generate_patch "$tmp_task" "$run_dir"
	local rc=$?
	rm -f "$tmp_task"
	return $rc
}

# ---------------------------------------------------------------------------
# coder_status
# ---------------------------------------------------------------------------
coder_status() {
	brand_header "Coder model status"
	brand_kv "provider" "${LEAF_CODER_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}"
	if leaf_runtime_export_selection >/dev/null 2>&1; then
		brand_kv "runtime coder" "$LEAF_CODER_MODEL_KEY ($LEAF_CODER_MODEL_QUANT)"
		brand_kv "worker tiers" "$(jq -r '[.[].name] | join(", ")' <<< "$LEAF_RUNTIME_WORKERS_JSON")"
	fi
	brand_kv "max_lines" "${LEAF_PATCH_MAX_LINES:-400}"
	brand_kv "max_files" "${LEAF_PATCH_MAX_FILES:-20}"
	brand_kv "max_del_ratio" "${LEAF_PATCH_MAX_DELETE_RATIO:-0.5}"
	brand_kv "gate" "patch_validate (always runs before output)"
	printf '\n'
}
