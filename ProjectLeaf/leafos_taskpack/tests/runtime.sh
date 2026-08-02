#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT_DIR/bin/leafctl" runtime validate >/tmp/leafos_runtime_validate.out

selection="$("$ROOT_DIR/bin/leafctl" runtime select --json)"
printf '%s' "$selection" | jq -e '
	.selection.main_model.key == "gemma4-it-opus"
	and .selection.scheduler_model.key == "gemma4-it-opus"
	and .selection.coder_model.key == "gemma4-coder"
	and .selection.role_policy.coding_model_key == "gemma4-coder"
	and .selection.persona.key == "monday"
	and .selection.medium_moe.active_route == "incumbent"
	and .selection.medium_moe.automatic_promotion == false
	and .selection.medium_moe.candidate_status == "template"
	and .selection.medium_moe.candidate_resolved == false
	and (.selection.workers | length) == 6
' >/dev/null

models="$("$ROOT_DIR/bin/leafctl" runtime models --json)"
printf '%s' "$models" | jq -e '
	(.coder_models | length) == 1
	and .coder_models[0].key == "gemma4-coder"
	and ([.main_models[].key] | index("gemma4-it-opus"))
	and ([.scheduler_models[].key] | index("gemma4-it-opus"))
' >/dev/null

friday="$("$ROOT_DIR/bin/leafctl" runtime select --persona friday --json)"
printf '%s' "$friday" | jq -e '
	.selection.persona.code_policy == "avoid_unless_stuck"
	and (.selection.workers | length) == 0
' >/dev/null

event="$("$ROOT_DIR/bin/leafctl" runtime event plan 0.86 "plan text")"
printf '%s' "$event" | jq -e '
	keys == ["confidence_score","content","response_type"]
	and .response_type == "plan"
	and .confidence_score == "0.86"
' >/dev/null

workers="$("$ROOT_DIR/bin/leafctl" runtime workers 0.42 tests_failed --json)"
printf '%s' "$workers" | jq -e '
	[.workers[].name] | index("reviewer") and index("hardcheck")
' >/dev/null

echo "runtime tests passed"
