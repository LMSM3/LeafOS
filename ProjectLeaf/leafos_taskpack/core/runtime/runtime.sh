#!/usr/bin/env bash
# core/runtime/runtime.sh
# Canonical LeafOS runtime selector: main model + coder swarm + persona.

set -uo pipefail

_RUNTIME_ROOT="${_RUNTIME_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

source "$_RUNTIME_ROOT/core/brand/brand.sh"

LEAF_RUNTIME_CONFIG="${LEAF_RUNTIME_CONFIG:-$_RUNTIME_ROOT/config/runtime.json}"

_leaf_runtime_require_jq() {
	command -v jq &>/dev/null || {
		brand_die "runtime: jq is required for runtime selection."
	}
}

_leaf_runtime_config() {
	[[ -f "$LEAF_RUNTIME_CONFIG" ]] || brand_die "runtime config not found: $LEAF_RUNTIME_CONFIG"
	printf '%s\n' "$LEAF_RUNTIME_CONFIG"
}

_leaf_runtime_default() {
	local key="$1"
	_leaf_runtime_require_jq
	jq -r --arg key "$key" '.leafos_runtime.defaults[$key] // empty' "$(_leaf_runtime_config)"
}

_leaf_runtime_known_main() {
	local key="$1"
	jq -e --arg key "$key" '.leafos_runtime.main_models[] | select(.key == $key)' "$(_leaf_runtime_config)" >/dev/null
}

_leaf_runtime_known_scheduler() {
	local key="$1"
	jq -e --arg key "$key" '.leafos_runtime.main_models[] | select(.key == $key)' "$(_leaf_runtime_config)" >/dev/null
}

_leaf_runtime_known_coder() {
	local key="$1"
	jq -e --arg key "$key" '.leafos_runtime.coder_models[] | select(.key == $key)' "$(_leaf_runtime_config)" >/dev/null
}

_leaf_runtime_known_persona() {
	local key="$1"
	jq -e --arg key "$key" '.leafos_runtime.persona_registry[] | select(.key == $key)' "$(_leaf_runtime_config)" >/dev/null
}

_leaf_runtime_known_mode() {
	local key="$1"
	jq -e --arg key "$key" '.leafos_runtime.modes | index($key)' "$(_leaf_runtime_config)" >/dev/null
}

leaf_runtime_select() {
	local main="" scheduler="" coder="" persona="" mode="" coding_language="" coding_model_choice="" coding_tier="" json=0

	while [[ $# -gt 0 ]]; do
		case "$1" in
			--main)    [[ $# -ge 2 ]] || brand_die "runtime select --main requires KEY"; main="$2"; shift 2 ;;
			--main=*)  main="${1#--main=}"; shift ;;
			--scheduler)    [[ $# -ge 2 ]] || brand_die "runtime select --scheduler requires KEY"; scheduler="$2"; shift 2 ;;
			--scheduler=*)  scheduler="${1#--scheduler=}"; shift ;;
			--coder)   [[ $# -ge 2 ]] || brand_die "runtime select --coder requires KEY"; coder="$2"; shift 2 ;;
			--coder=*) coder="${1#--coder=}"; shift ;;
			--persona) [[ $# -ge 2 ]] || brand_die "runtime select --persona requires KEY"; persona="$2"; shift 2 ;;
			--persona=*) persona="${1#--persona=}"; shift ;;
			--mode)    [[ $# -ge 2 ]] || brand_die "runtime select --mode requires MODE"; mode="$2"; shift 2 ;;
			--mode=*)  mode="${1#--mode=}"; shift ;;
			--language)    [[ $# -ge 2 ]] || brand_die "runtime select --language requires LANG"; coding_language="$2"; shift 2 ;;
			--language=*)  coding_language="${1#--language=}"; shift ;;
			--coding-model)    [[ $# -ge 2 ]] || brand_die "runtime select --coding-model requires KEY"; coding_model_choice="$2"; shift 2 ;;
			--coding-model=*)  coding_model_choice="${1#--coding-model=}"; shift ;;
			--coding-tier)    [[ $# -ge 2 ]] || brand_die "runtime select --coding-tier requires TIER"; coding_tier="$2"; shift 2 ;;
			--coding-tier=*)  coding_tier="${1#--coding-tier=}"; shift ;;
			--json)    json=1; shift ;;
			*) brand_die "runtime select: unknown flag: $1" ;;
		esac
	done

	_leaf_runtime_require_jq
	main="${main:-${LEAF_MAIN_MODEL:-$(_leaf_runtime_default main_model)}}"
	scheduler="${scheduler:-${LEAF_SCHEDULER_MODEL:-$(_leaf_runtime_default scheduler_model)}}"
	coder="${coder:-${LEAF_CODER_MODEL:-$(_leaf_runtime_default coder_model)}}"
	coding_language="${coding_language:-${LEAF_CODING_LANGUAGE:-$(_leaf_runtime_default coding_language)}}"
	coding_model_choice="${coding_model_choice:-${LEAF_CODING_MODEL_CHOICE:-$(_leaf_runtime_default coding_model_choice)}}"
	coding_tier="${coding_tier:-${LEAF_CODING_TIER:-$(_leaf_runtime_default coding_tier)}}"
	persona="${persona:-${LEAF_PERSONA:-$(_leaf_runtime_default persona)}}"
	mode="${mode:-${LEAF_RUNTIME_MODE:-$(_leaf_runtime_default mode)}}"

	_leaf_runtime_known_main "$main" || brand_die "runtime: unknown main model: $main"
	_leaf_runtime_known_scheduler "$scheduler" || brand_die "runtime: unknown scheduler model: $scheduler"
	_leaf_runtime_known_coder "$coder" || brand_die "runtime: unknown coder model: $coder"
	_leaf_runtime_known_persona "$persona" || brand_die "runtime: unknown persona: $persona"
	_leaf_runtime_known_mode "$mode" || brand_die "runtime: unknown mode: $mode"

	local fable_coder
	fable_coder="$(jq -r '.leafos_runtime.role_policy.coding_model_key // "gemma4-coder"' "$(_leaf_runtime_config)")"
	[[ "$coder" == "$fable_coder" ]] || brand_die "runtime: coder model must be $fable_coder"
	[[ "$coding_model_choice" == "$fable_coder" ]] || brand_die "runtime: coding model choice must be $fable_coder"
	[[ "$main" != "$fable_coder" ]] || brand_die "runtime: Fable/Gemma4-Coder cannot be main model"
	[[ "$scheduler" != "$fable_coder" ]] || brand_die "runtime: Fable/Gemma4-Coder cannot be scheduler model"
	jq -e --arg lang "$coding_language" '.leafos_runtime.role_policy.allowed_coding_languages | index($lang)' "$(_leaf_runtime_config)" >/dev/null \
		|| brand_die "runtime: unsupported coding language: $coding_language"
	jq -e --arg coder "$coder" --arg tier "$coding_tier" '.leafos_runtime.coder_models[] | select(.key == $coder) | .tiers[] | select(.name == $tier)' "$(_leaf_runtime_config)" >/dev/null \
		|| brand_die "runtime: unknown coding tier for $coder: $coding_tier"

	local selection
	local moe_policy_path="$_RUNTIME_ROOT/config/medium_moe_policy.json"
	local moe_candidate_path="${LEAF_MEDIUM_MOE_CANDIDATE:-$_RUNTIME_ROOT/config/medium_moe_candidate.template.json}"
	local moe_policy_json='{}' moe_candidate_json='{}'
	[[ -f "$moe_policy_path" ]] && moe_policy_json="$(jq -c '.' "$moe_policy_path")"
	[[ -f "$moe_candidate_path" ]] && moe_candidate_json="$(jq -c '.' "$moe_candidate_path")"
	selection="$(jq -c \
		--arg main "$main" \
		--arg scheduler "$scheduler" \
		--arg coder "$coder" \
		--arg coding_language "$coding_language" \
		--arg coding_model_choice "$coding_model_choice" \
		--arg coding_tier "$coding_tier" \
		--arg persona "$persona" \
		--arg mode "$mode" \
		--arg candidate_path "$moe_candidate_path" \
		--argjson moe_policy "$moe_policy_json" \
		--argjson moe_candidate "$moe_candidate_json" \
		'
		.leafos_runtime as $rt
		| ($rt.main_models[] | select(.key == $main)) as $main_obj
		| ($rt.main_models[] | select(.key == $scheduler)) as $scheduler_obj
		| ($rt.coder_models[] | select(.key == $coder)) as $coder_obj
		| ($rt.persona_registry[] | select(.key == $persona)) as $persona_obj
		| {
			schema_version,
			selection: {
				main_model: $main_obj,
				scheduler_model: $scheduler_obj,
				coder_model: $coder_obj,
				coding_choice: {
					language: $coding_language,
					model_key: $coding_model_choice,
					tier: $coding_tier,
					backend: "python",
					source: "runtime-default-or-env"
				},
				persona: $persona_obj,
				mode: $mode,
				language_hint: $coding_language,
				care_mode: $persona_obj.care_mode,
				contract_version: $rt.output_contract.version,
				role_policy: $rt.role_policy,
				workers: (
					if $persona_obj.code_policy == "avoid_unless_stuck"
					then []
					else $coder_obj.tiers
					end
				),
				medium_moe: {
					policy_id: ($moe_policy.policy_id // null),
					preferred_architecture: ($moe_policy.decision.preferred_architecture // null),
					parameter_band_billion: ($moe_policy.decision.total_parameter_band_billion // null),
					incumbent_route: ($moe_policy.decision.incumbent_route // null),
					automatic_promotion: false,
					active_route: "incumbent",
					candidate_path: $candidate_path,
					candidate_status: ($moe_candidate.status // "unavailable"),
					candidate_resolved: (($moe_candidate.status // "") == "resolved")
				},
				notes: (
					if $persona_obj.code_policy == "avoid_unless_stuck"
					then ["coder swarm suppressed until explicit stuck signal"]
					else []
					end
				)
			}
		}
		' "$(_leaf_runtime_config)")"

	if [[ "$json" == "1" ]]; then
		printf '%s\n' "$selection"
		return 0
	fi

	brand_header "LeafOS runtime selection"
	brand_kv "main" "$(jq -r '.selection.main_model.key + " (" + .selection.main_model.quant + ")"' <<< "$selection")"
	brand_kv "scheduler" "$(jq -r '.selection.scheduler_model.key + " (" + .selection.scheduler_model.quant + ")"' <<< "$selection")"
	brand_kv "coder" "$(jq -r '.selection.coder_model.key + " (" + .selection.coder_model.default_quant + ")"' <<< "$selection")"
	brand_kv "coding choice" "$(jq -r '.selection.coding_choice.language + " / " + .selection.coding_choice.model_key + " / " + .selection.coding_choice.tier' <<< "$selection")"
	brand_kv "persona" "$(jq -r '.selection.persona.key + " / " + .selection.persona.voice' <<< "$selection")"
	brand_kv "mode" "$(jq -r '.selection.mode' <<< "$selection")"
	brand_kv "language hint" "$(jq -r '.selection.language_hint' <<< "$selection")"
	brand_kv "care mode" "$(jq -r '.selection.care_mode' <<< "$selection")"
	brand_kv "workers" "$(jq -r '[.selection.workers[].name] | if length == 0 then "suppressed" else join(", ") end' <<< "$selection")"
	jq -r '.selection.notes[]? | "  note: " + .' <<< "$selection"
}

leaf_runtime_export_selection() {
	local selection
	selection="$(leaf_runtime_select --json "$@")" || return $?
	export LEAF_MAIN_MODEL_KEY
	LEAF_MAIN_MODEL_KEY="$(jq -r '.selection.main_model.key' <<< "$selection")"
	export LEAF_MAIN_MODEL_REPO
	LEAF_MAIN_MODEL_REPO="$(jq -r '.selection.main_model.repo' <<< "$selection")"
	export LEAF_MAIN_MODEL_QUANT
	LEAF_MAIN_MODEL_QUANT="$(jq -r '.selection.main_model.quant' <<< "$selection")"
	export LEAF_SCHEDULER_MODEL_KEY
	LEAF_SCHEDULER_MODEL_KEY="$(jq -r '.selection.scheduler_model.key' <<< "$selection")"
	export LEAF_SCHEDULER_MODEL_REPO
	LEAF_SCHEDULER_MODEL_REPO="$(jq -r '.selection.scheduler_model.repo' <<< "$selection")"
	export LEAF_SCHEDULER_MODEL_QUANT
	LEAF_SCHEDULER_MODEL_QUANT="$(jq -r '.selection.scheduler_model.quant' <<< "$selection")"
	export LEAF_CODER_MODEL_KEY
	LEAF_CODER_MODEL_KEY="$(jq -r '.selection.coder_model.key' <<< "$selection")"
	export LEAF_CODER_MODEL_REPO
	LEAF_CODER_MODEL_REPO="$(jq -r '.selection.coder_model.repo' <<< "$selection")"
	export LEAF_CODER_MODEL_QUANT
	LEAF_CODER_MODEL_QUANT="$(jq -r '.selection.coder_model.default_quant' <<< "$selection")"
	export LEAF_CODING_LANGUAGE
	LEAF_CODING_LANGUAGE="$(jq -r '.selection.coding_choice.language' <<< "$selection")"
	export LEAF_CODING_MODEL_CHOICE
	LEAF_CODING_MODEL_CHOICE="$(jq -r '.selection.coding_choice.model_key' <<< "$selection")"
	export LEAF_CODING_TIER
	LEAF_CODING_TIER="$(jq -r '.selection.coding_choice.tier' <<< "$selection")"
	export LEAF_PERSONA_KEY
	LEAF_PERSONA_KEY="$(jq -r '.selection.persona.key' <<< "$selection")"
	export LEAF_PERSONA_CODE_POLICY
	LEAF_PERSONA_CODE_POLICY="$(jq -r '.selection.persona.code_policy' <<< "$selection")"
	export LEAF_PERSONA_DEFAULT_LANGUAGE
	LEAF_PERSONA_DEFAULT_LANGUAGE="$(jq -r '.selection.persona.default_language' <<< "$selection")"
	export LEAF_RUNTIME_CARE_MODE
	LEAF_RUNTIME_CARE_MODE="$(jq -r '.selection.care_mode' <<< "$selection")"
	export LEAF_RUNTIME_WORKERS_JSON
	LEAF_RUNTIME_WORKERS_JSON="$(jq -c '.selection.workers' <<< "$selection")"
}

leaf_runtime_validate() {
	_leaf_runtime_require_jq
	jq -e '
		. as $doc
		| .schema_version == 1
		and ($doc.leafos_runtime.output_contract.required_keys == ["response_type","content","confidence_score"])
		and ($doc.leafos_runtime.main_models | length > 0)
		and ($doc.leafos_runtime.coder_models | length == 1)
		and ($doc.leafos_runtime.coder_models[0].key == $doc.leafos_runtime.role_policy.coding_model_key)
		and ($doc.leafos_runtime.defaults.coding_language == "python")
		and ($doc.leafos_runtime.role_policy.allowed_coding_languages | index($doc.leafos_runtime.defaults.coding_language))
		and ($doc.leafos_runtime.defaults.coding_model_choice == $doc.leafos_runtime.role_policy.coding_model_key)
		and ($doc.leafos_runtime.defaults.scheduler_model as $s | [$doc.leafos_runtime.main_models[].key] | index($s))
		and ($doc.leafos_runtime.defaults.scheduler_model as $s | [$doc.leafos_runtime.coder_models[].key] | index($s) | not)
		and ($doc.leafos_runtime.persona_registry | length > 0)
	' "$(_leaf_runtime_config)" >/dev/null || brand_die "runtime config failed structural validation"
	leaf_runtime_select --json >/dev/null
	brand_ok "runtime config valid: $LEAF_RUNTIME_CONFIG"
}

leaf_runtime_personas() {
	local json=0
	[[ "${1:-}" == "--json" ]] && json=1
	_leaf_runtime_require_jq
	if [[ "$json" == "1" ]]; then
		jq -c '.leafos_runtime.persona_registry' "$(_leaf_runtime_config)"
	else
		brand_header "LeafOS personas"
		jq -r '
			.leafos_runtime.persona_registry[]
			| "  \(.key)\t\(.voice)\tpolicy=\(.code_policy)\tlanguage=\(.default_language)"
		' "$(_leaf_runtime_config)"
	fi
}

leaf_runtime_models() {
	local json=0
	[[ "${1:-}" == "--json" ]] && json=1
	_leaf_runtime_require_jq
	if [[ "$json" == "1" ]]; then
		jq -c '{main_models:.leafos_runtime.main_models, scheduler_models:.leafos_runtime.main_models, coder_models:.leafos_runtime.coder_models, role_policy:.leafos_runtime.role_policy}' "$(_leaf_runtime_config)"
	else
		brand_header "LeafOS runtime models"
		printf '  main models\n'
		jq -r '.leafos_runtime.main_models[] | "    \(.key)\t\(.role)\t\(.quant)"' "$(_leaf_runtime_config)"
		printf '\n  scheduler models\n'
		jq -r '.leafos_runtime.main_models[] | "    \(.key)\t\(.role)\t\(.quant)"' "$(_leaf_runtime_config)"
		printf '\n  coder models\n'
		jq -r '.leafos_runtime.coder_models[] | "    \(.key)\t\(.role)\tdefault=\(.default_quant)"' "$(_leaf_runtime_config)"
	fi
}

_leaf_runtime_confidence_valid() {
	local confidence="$1"
	awk -v c="$confidence" 'BEGIN { exit !(c ~ /^[0-9]+([.][0-9]+)?$/ && c >= 0 && c <= 1) }'
}

leaf_runtime_event() {
	local response_type="${1:-}"
	local confidence="${2:-}"
	shift 2 2>/dev/null || true
	local content="$*"

	[[ -n "$response_type" ]] || brand_die "runtime event requires RESPONSE_TYPE CONFIDENCE CONTENT"
	[[ -n "$confidence" ]] || brand_die "runtime event requires CONFIDENCE"
	[[ -n "$content" ]] || content=""
	_leaf_runtime_require_jq
	jq -e --arg rt "$response_type" '.leafos_runtime.output_contract.allowed_response_types | index($rt)' "$(_leaf_runtime_config)" >/dev/null \
		|| brand_die "runtime event: invalid response_type: $response_type"
	_leaf_runtime_confidence_valid "$confidence" || brand_die "runtime event: confidence_score must be 0.0 through 1.0"

	jq -cn \
		--arg response_type "$response_type" \
		--arg content "$content" \
		--arg confidence_score "$confidence" \
		'{response_type:$response_type, content:$content, confidence_score:$confidence_score}'
}

leaf_runtime_workers() {
	local confidence="${1:-}"
	shift || true
	local coder="" json=0
	local reasons=()
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--coder) [[ $# -ge 2 ]] || brand_die "runtime workers --coder requires KEY"; coder="$2"; shift 2 ;;
			--coder=*) coder="${1#--coder=}"; shift ;;
			--json) json=1; shift ;;
			*) reasons+=("$1"); shift ;;
		esac
	done

	[[ -n "$confidence" ]] || brand_die "runtime workers requires CONFIDENCE"
	_leaf_runtime_confidence_valid "$confidence" || brand_die "runtime workers: confidence must be 0.0 through 1.0"
	_leaf_runtime_require_jq
	coder="${coder:-${LEAF_CODER_MODEL:-$(_leaf_runtime_default coder_model)}}"
	_leaf_runtime_known_coder "$coder" || brand_die "runtime workers: unknown coder model: $coder"

	local names=(scout sketch builder)
	if awk -v c="$confidence" 'BEGIN { exit !(c < 0.8) }'; then
		names+=(reviewer)
	fi
	if awk -v c="$confidence" 'BEGIN { exit !(c < 0.5) }'; then
		names+=(hardcheck)
	fi
	if [[ ${#reasons[@]} -gt 0 ]]; then
		names+=(reviewer hardcheck)
	fi
	local reason
	for reason in "${reasons[@]}"; do
		case "$reason" in
			finalizer|final_pass|checkpoint) names+=(finalizer) ;;
		esac
	done

	local names_json
	names_json="$(printf '%s\n' "${names[@]}" | jq -R . | jq -s 'unique')"
	local workers
	workers="$(jq -c \
		--arg coder "$coder" \
		--argjson names "$names_json" \
		'
		.leafos_runtime.coder_models[]
		| select(.key == $coder)
		| .tiers
		| map(select(.name as $n | $names | index($n)))
		' "$(_leaf_runtime_config)")"

	if [[ "$json" == "1" ]]; then
		jq -cn \
			--arg confidence_score "$confidence" \
			--arg coder_model "$coder" \
			--argjson reasons "$(printf '%s\n' "${reasons[@]}" | jq -R . | jq -s .)" \
			--argjson workers "$workers" \
			'{confidence_score:$confidence_score, coder_model:$coder_model, reasons:$reasons, workers:$workers}'
	else
		brand_header "LeafOS worker tier plan"
		brand_kv "confidence" "$confidence"
		brand_kv "coder" "$coder"
		[[ ${#reasons[@]} -gt 0 ]] && brand_kv "forced by" "${reasons[*]}"
		jq -r '.[] | "  \(.name)\t\(.quant)\t\(.mode)\t\(.purpose)"' <<< "$workers"
	fi
}

leaf_runtime_prompt_preamble() {
	_leaf_runtime_require_jq
	local selection
	selection="$(leaf_runtime_select --json 2>/dev/null)" || return 0
	printf 'LeafOS runtime selection:\n'
	jq -r '
		"Main model: \(.selection.main_model.key) role=\(.selection.main_model.role)",
		"Scheduler model: \(.selection.scheduler_model.key) role=\(.selection.scheduler_model.role)",
		"Coder model: \(.selection.coder_model.key) role=\(.selection.coder_model.role)",
		"Persona: \(.selection.persona.key) voice=\(.selection.persona.voice) code_policy=\(.selection.persona.code_policy)",
		"Care mode: \(.selection.care_mode)",
		"Role policy: Fable/Gemma4-Coder is coding-only; scheduler uses the main model pool",
		"Output contract: response_type/content/confidence_score only"
	' <<< "$selection"
	printf '\n'
}
