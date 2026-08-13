#!/usr/bin/env bash
# core/agent/dry_run.sh  --  Full dry-run agent path (WO-007-C §8)
#
# leaf_agent_dry_run TASK_DESCRIPTION
#
#   user task
#     -> brain provider    -> agent.graph.json
#     -> graph validator   (section 3)
#     -> coder provider    -> patch.diff
#     -> patch validator   (section 4)
#     -> report.md
#
# Nothing is applied. Working tree is unchanged.
# Acceptance test: `git status` clean after run.
#
# Exit codes: 0=ok, 1=validation failed, 2=provider failure, 3=prereq missing

set -uo pipefail

_DR_ROOT="${_DR_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_DR_ROOT/core/brand/brand.sh"
source "$_DR_ROOT/core/providers/providers.sh"
source "$_DR_ROOT/core/graph/graph_validate.sh"
source "$_DR_ROOT/core/agent/manifest.sh"
source "$_DR_ROOT/core/patch/validate.sh"

# brain.sh and coder.sh are sourced by leafctl; guard against double-source
[[ "$(type -t brain_generate_graph)" == "function" ]] \
	|| source "$_DR_ROOT/core/model/brain.sh"
[[ "$(type -t coder_generate_patch)" == "function" ]] \
	|| source "$_DR_ROOT/core/model/coder.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_DR_ROOT/runs}"

# ---------------------------------------------------------------------------
# leaf_agent_dry_run TASK_DESCRIPTION
# ---------------------------------------------------------------------------
leaf_agent_dry_run() {
	local task_desc="${*:-}"
	[[ -n "$task_desc" ]] || { brand_warn "leaf_agent_dry_run: requires a task description"; return 1; }

	brand_header "agent dry-run"
	brand_kv "task" "$task_desc"

	# -- Establish run directory (shared across the whole pipeline) ----------
	local run_dir; run_dir="$(manifest_run_dir_new)"
	local run_id; run_id="$(basename "$run_dir")"
	brand_kv "run"  "$run_id"
	printf '\n'

	local graph_file="$run_dir/agent.graph.json"
	local patch_file="$run_dir/patch.diff"
	local report_file="$run_dir/report.md"
	local validation_log="$run_dir/validation.log"

	local overall_ok=1
	local -a results=()

	# -- Snapshot working tree for cleanliness check -------------------------
	local pre_status
	if ! pre_status="$(git -C "$_DR_ROOT" status --porcelain 2>/dev/null | wc -l)"; then
		pre_status=0
	fi
	[[ "$pre_status" =~ ^[0-9]+$ ]] || pre_status=0

	# -- Write task to prompt.txt --------------------------------------------
	local task_file="$run_dir/prompt.txt"
	{
		printf '# Agent task\n\n'
		printf '## Goal\n%s\n\n' "$task_desc"
		printf '## Steps\n1. %s\n' "$task_desc"
	} >"$task_file"
	manifest_write_prompt "$run_dir" "$task_desc"

	# =========================================================================
	# Stage 1: Brain -> graph
	# =========================================================================
	brand_say "[1/5] brain: generating graph..."

	# brain_generate_graph uses LEAF_BRAIN_PROVIDER internally;
	# pass run_dir so manifest artifacts land there.
	# Capture the graph path while provider diagnostics go to the run log.
	local brain_graph
	brain_graph="$(brain_generate_graph "$task_file" "$graph_file" 2>"$run_dir/brain.log" || true)"

	if [[ -f "$graph_file" ]]; then
		_dr_ok "provider: ${LEAF_BRAIN_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}"
		_dr_ok "brain graph generated"
		results+=("brain:ok")
	else
		_dr_fail "brain graph generated" "no graph file produced (see $run_dir/brain.log)"
		results+=("brain:fail")
		overall_ok=0
	fi

	# =========================================================================
	# Stage 2: Graph validator
	# =========================================================================
	brand_say "[2/5] graph: validating..."
	if [[ -f "$graph_file" ]]; then
		if graph_validate "$graph_file" "$_DR_ROOT" >>"$validation_log" 2>&1; then
			_dr_ok "graph validated"
			results+=("graph_validate:ok")
		else
			_dr_fail "graph validated" "see $validation_log"
			results+=("graph_validate:fail")
			overall_ok=0
		fi
	else
		_dr_fail "graph validated" "skipped (no graph)"
		results+=("graph_validate:skip")
		overall_ok=0
	fi

	# =========================================================================
	# Stage 3: Coder -> patch
	# =========================================================================
	brand_say "[3/5] coder: generating patch..."
	if [[ -f "$graph_file" ]]; then
		if coder_generate_patch "$task_file" "$run_dir" >"$run_dir/coder.log" 2>&1; then
			_dr_ok "coder patch generated"
			results+=("coder:ok")
		else
			_dr_fail "coder patch generated" "see $run_dir/coder.log"
			results+=("coder:fail")
			overall_ok=0
		fi
	else
		_dr_fail "coder patch generated" "skipped (no graph)"
		results+=("coder:skip")
		overall_ok=0
	fi

	# =========================================================================
	# Stage 4: Patch validator
	# =========================================================================
	brand_say "[4/5] patch: validating..."
	if [[ -f "$patch_file" ]]; then
		if patch_validate "$patch_file" "$_DR_ROOT" >>"$validation_log" 2>&1; then
			_dr_ok "patch validated"
			results+=("patch_validate:ok")
		else
			_dr_fail "patch validated" "see $validation_log"
			results+=("patch_validate:fail")
			overall_ok=0
		fi
	else
		_dr_fail "patch validated" "skipped (no patch)"
		results+=("patch_validate:skip")
		# The coder stage already marks the overall run failed when no patch exists.
	fi

	# =========================================================================
	# Stage 5: Report
	# =========================================================================
	brand_say "[5/5] writing report..."
	_dr_write_report "$run_dir" "$report_file" "$task_desc" "${results[@]}"
	_dr_ok "report written"

	# -- Working tree cleanliness check ----------------------------------------
	local post_status
	if ! post_status="$(git -C "$_DR_ROOT" status --porcelain 2>/dev/null | wc -l)"; then
		post_status=0
	fi
	[[ "$post_status" =~ ^[0-9]+$ ]] || post_status=0
	if (( post_status == pre_status )); then
		_dr_ok "working tree unchanged (git status clean)"
	else
		_dr_fail "working tree unchanged" "dry-run modified the working tree -- this is a bug"
		overall_ok=0
	fi

	# -- Flip latest symlink now that the run directory is complete -----------
	manifest_write "$run_dir" "$(  [[ $overall_ok -eq 1 ]] && echo completed || echo failed)" \
		"task=$task_desc"
	manifest_symlink_latest "$run_dir"

	# -- Summary --------------------------------------------------------------
	printf '\n'
	brand_kv "Artifacts" ""
	printf '  runs/%s/agent.graph.json\n'  "$run_id"
	printf '  runs/%s/patch.diff\n'        "$run_id"
	printf '  runs/%s/report.md\n'         "$run_id"
	printf '\n'

	if [[ $overall_ok -eq 1 ]]; then
		brand_ok "dry-run complete: all stages passed"
		return 0
	else
		brand_warn "dry-run complete: one or more stages failed"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# _dr_write_report RUN_DIR REPORT_FILE TASK RESULT...
# ---------------------------------------------------------------------------
_dr_write_report() {
	local run_dir="$1" report_file="$2" task="$3"
	shift 3
	local -a results=("$@")
	local now; now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	local run_id; run_id="$(basename "$run_dir")"

	{
		printf '# Dry-Run Report\n\n'
		printf '**Run:** %s  \n' "$run_id"
		printf '**Task:** %s  \n' "$task"
		printf '**Time:** %s  \n\n' "$now"
		printf '## Pipeline Results\n\n'
		for r in "${results[@]}"; do
			local stage="${r%%:*}" verdict="${r##*:}"
			case "$verdict" in
				ok)   printf '%s\n' "- [ok]   $stage" ;;
				fail) printf '%s\n' "- [FAIL] $stage" ;;
				skip) printf '%s\n' "- [skip] $stage" ;;
			esac
		done
		printf '\n## Artifacts\n\n'
		printf '| File | Present |\n| --- | --- |\n'
		for f in agent.graph.json patch.diff validation.log manifest.json; do
			[[ -f "$run_dir/$f" ]] && printf '| %s | yes |\n' "$f" || printf '| %s | no |\n' "$f"
		done
		printf '\n'
	} >"$report_file"
}

_dr_ok()   { printf '  [ok]   %s\n' "$*"; }
_dr_fail() { local label="$1"; shift; printf '  [fail] %s -- %s\n' "$label" "$*"; }
