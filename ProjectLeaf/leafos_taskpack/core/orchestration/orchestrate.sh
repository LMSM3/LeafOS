#!/usr/bin/env bash
# LeafOS 0.3 orchestration prototype.
# Inputs are exactly three files: README, SKELETON, and WILDCARD.
# The model proposes JSON actions. It never supplies shell commands.

set -uo pipefail

_ORCH_ROOT="${_ORCH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_ORCH_ROOT/core/brand/brand.sh"

LEAF_ORCHESTRATION_RUNS_DIR="${LEAF_ORCHESTRATION_RUNS_DIR:-$_ORCH_ROOT/runs}"
LEAF_ORCHESTRATION_SCHEMA="${LEAF_ORCHESTRATION_SCHEMA:-$_ORCH_ROOT/config/orchestration.action.schema.json}"
LEAF_ORCHESTRATION_GRAMMAR="${LEAF_ORCHESTRATION_GRAMMAR:-$_ORCH_ROOT/config/orchestration.action.gbnf}"
LEAF_ORCHESTRATION_PROVIDER="${LEAF_ORCHESTRATION_PROVIDER:-${LEAF_BRAIN_PROVIDER:-${LEAF_PROVIDER_MODE:-off}}}"
LEAF_LLAMACPP_URL="${LEAF_LLAMACPP_URL:-http://127.0.0.1:8080}"
LEAF_LLAMACPP_CHAT_URL="${LEAF_LLAMACPP_CHAT_URL:-$LEAF_LLAMACPP_URL/v1/chat/completions}"
LEAF_LLAMACPP_MODEL="${LEAF_LLAMACPP_MODEL:-local}"
LEAF_ORCHESTRATION_MAX_TEXT_BYTES="${LEAF_ORCHESTRATION_MAX_TEXT_BYTES:-65536}"
LEAF_AI_TIMEOUT_SEC="${LEAF_AI_TIMEOUT_SEC:-120}"

_orch_abs_file() {
	local path="$1"
	[[ "$path" = /* ]] || path="$PWD/$path"
	[[ -f "$path" ]] || return 1
	local dir base
	dir="$(cd "$(dirname "$path")" 2>/dev/null && pwd)" || return 1
	base="$(basename "$path")"
	printf '%s/%s\n' "$dir" "$base"
}

_orch_hash() {
	local file="$1"
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$file" | awk '{print $1}'
	elif command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$file" | awk '{print $1}'
	elif command -v python3 >/dev/null 2>&1; then
		python3 - "$file" <<'PY'
import hashlib
import sys

h = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        h.update(block)
print(h.hexdigest())
PY
	else
		return 1
	fi
}

_orch_kind() {
	local file="$1"
	if [[ ! -s "$file" ]]; then
		printf 'empty\n'
	elif LC_ALL=C grep -Iq . "$file" 2>/dev/null; then
		printf 'text\n'
	else
		printf 'binary\n'
	fi
}

_orch_snapshot_inputs() {
	local run_dir="$1" readme="$2" skeleton="$3" wildcard="$4"
	mkdir -p "$run_dir/context" "$run_dir/artifacts"
	cp -- "$readme" "$run_dir/context/readme"
	cp -- "$skeleton" "$run_dir/context/skeleton"
	cp -- "$wildcard" "$run_dir/context/wildcard"

	local rh sh wh
	rh="$(_orch_hash "$readme")" || return 1
	sh="$(_orch_hash "$skeleton")" || return 1
	wh="$(_orch_hash "$wildcard")" || return 1

	jq -n \
		--arg protocol "leafos.orchestration.context.v0.3" \
		--arg run_dir "$run_dir" \
		--arg readme "$readme" --arg skeleton "$skeleton" --arg wildcard "$wildcard" \
		--arg rh "$rh" --arg sh "$sh" --arg wh "$wh" \
		--arg rt "$(_orch_kind "$readme")" --arg st "$(_orch_kind "$skeleton")" --arg wt "$(_orch_kind "$wildcard")" \
		--argjson rb "$(wc -c < "$readme")" --argjson sb "$(wc -c < "$skeleton")" --argjson wb "$(wc -c < "$wildcard")" \
		'{
			protocol: $protocol,
			run_dir: $run_dir,
			inputs: {
				readme: {source: $readme, snapshot: ($run_dir + "/context/readme"), bytes: $rb, kind: $rt, sha256: $rh},
				skeleton: {source: $skeleton, snapshot: ($run_dir + "/context/skeleton"), bytes: $sb, kind: $st, sha256: $sh},
				wildcard: {source: $wildcard, snapshot: ($run_dir + "/context/wildcard"), bytes: $wb, kind: $wt, sha256: $wh}
			}
		}' > "$run_dir/context.json"
}

_orch_excerpt() {
	local file="$1"
	if [[ "$(_orch_kind "$file")" == "text" ]]; then
		head -c "$LEAF_ORCHESTRATION_MAX_TEXT_BYTES" "$file"
		printf '\n'
	else
		printf '[binary or empty input; metadata only]\n'
	fi
}

_orch_build_prompt() {
	local run_dir="$1"
	{
		printf '%s\n' \
			'You are the LeafOS 0.3 orchestration planner.' \
			'Return one JSON object only. Do not return Markdown, shell, code fences, or explanations.' \
			'Choose only the declared skills. Never invent a command, path, skill, or input reference.' \
			'The executor validates this object and may refuse every action.'
		printf '\nJSON protocol and input manifest:\n'
		cat "$run_dir/context.json"
		printf '\nREADME snapshot excerpt:\n'
		_orch_excerpt "$run_dir/context/readme"
		printf '\nSkeleton snapshot excerpt:\n'
		_orch_excerpt "$run_dir/context/skeleton"
		printf '\nWildcard input metadata is in the manifest. Use file.hash unless its kind is text.\n'
	} > "$run_dir/prompt.txt"
}

_orch_mock_plan() {
	local run_dir="$1"
	local goal
	goal="$(jq -r '.inputs.readme.source | "Orchestrate three inputs: " + .' "$run_dir/context.json")"
	jq -n --arg goal "$goal" '{
		protocol: "leafos.orchestration.v0.3",
		goal: $goal,
		actions: [
			{id: "inspect_inputs", skill: "context.inspect", input: {}, depends_on: []},
			{id: "read_readme", skill: "file.read", input: {ref: "readme"}, depends_on: ["inspect_inputs"]},
			{id: "read_skeleton", skill: "file.read", input: {ref: "skeleton"}, depends_on: ["read_readme"]},
			{id: "hash_wildcard", skill: "file.hash", input: {ref: "wildcard"}, depends_on: ["read_skeleton"]},
			{id: "check_cli", skill: "check.run", input: {check: "shell-syntax"}, depends_on: ["hash_wildcard"]},
			{id: "write_report", skill: "report.write", input: {message: "Three-input orchestration completed."}, depends_on: ["check_cli"]}
		],
		completion: {required_actions: ["write_report"]}
}' > "$run_dir/plan.json"
}

_orch_llamacpp_plan() {
	local run_dir="$1"
	local schema response plan payload grammar
	schema="$(cat "$LEAF_ORCHESTRATION_SCHEMA")" || return 1
	payload="$(jq -n \
		--arg model "$LEAF_LLAMACPP_MODEL" \
		--arg system "Return only one JSON object conforming to the supplied LeafOS orchestration schema." \
		--arg user "$(cat "$run_dir/prompt.txt")" \
		--argjson schema "$schema" \
		--argjson temperature "${LEAF_PROVIDER_TEMPERATURE:-0.1}" \
		--argjson max_tokens "${LEAF_PROVIDER_MAX_TOKENS:-2048}" \
		'{model:$model, messages:[{role:"system",content:$system},{role:"user",content:$user}], temperature:$temperature, max_tokens:$max_tokens, stream:false, reasoning_format:"none", chat_template_kwargs:{enable_thinking:false}, response_format:{type:"json_schema",json_schema:{schema:$schema}}}')"
	response="$run_dir/llamacpp.response.json"
	if curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" "$LEAF_LLAMACPP_CHAT_URL" \
		-H 'Content-Type: application/json' -d "$payload" > "$response" 2>"$run_dir/llamacpp.error"; then
		plan="$(jq -r '.choices[0].message.content // empty' "$response" 2>/dev/null)"
		[[ -n "$plan" ]] || return 1
		printf '%s\n' "$plan" > "$run_dir/plan.json"
		return 0
	fi

	# Native completion endpoints can accept the schema directly.
	payload="$(jq -n \
		--arg prompt "$(cat "$run_dir/prompt.txt")" --argjson schema "$schema" \
		--argjson temperature "${LEAF_PROVIDER_TEMPERATURE:-0.1}" \
		--argjson n_predict "${LEAF_PROVIDER_MAX_TOKENS:-2048}" \
		'{prompt:$prompt,temperature:$temperature,n_predict:$n_predict,json_schema:$schema}')"
	if ! curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" "$LEAF_LLAMACPP_URL/completion" \
		-H 'Content-Type: application/json' -d "$payload" > "$response" 2>"$run_dir/llamacpp.error"; then
		[[ -f "$LEAF_ORCHESTRATION_GRAMMAR" ]] || return 1
		grammar="$(cat "$LEAF_ORCHESTRATION_GRAMMAR")" || return 1
		payload="$(jq -n \
			--arg prompt "$(cat "$run_dir/prompt.txt")" --arg grammar "$grammar" \
			--argjson temperature "${LEAF_PROVIDER_TEMPERATURE:-0.1}" \
			--argjson n_predict "${LEAF_PROVIDER_MAX_TOKENS:-2048}" \
			'{prompt:$prompt,temperature:$temperature,n_predict:$n_predict,grammar:$grammar}')"
		curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" "$LEAF_LLAMACPP_URL/completion" \
			-H 'Content-Type: application/json' -d "$payload" > "$response" 2>"$run_dir/llamacpp.error" || return 1
	fi
	plan="$(jq -r '.content // empty' "$response" 2>/dev/null)"
	[[ -n "$plan" ]] || return 1
	printf '%s\n' "$plan" > "$run_dir/plan.json"
}

_orch_model_plan() {
	local run_dir="$1"
	case "$LEAF_ORCHESTRATION_PROVIDER" in
		mock|offline)
			[[ "${LEAF_ENABLE_TEST_MOCK_PROVIDER:-0}" == "1" ]] || {
				brand_warn "orchestration: mock planning is test-only"
				return 2
			}
			_orch_mock_plan "$run_dir"
			;;
		llamacpp)     _orch_llamacpp_plan "$run_dir" ;;
		off)          brand_warn "orchestration: provider is disabled"; return 2 ;;
		*) brand_warn "orchestration: unsupported provider '$LEAF_ORCHESTRATION_PROVIDER'"; return 1 ;;
	esac
}

orchestration_plan_validate() {
	local plan="$1"
	jq empty "$plan" 2>/dev/null || return 1
	jq -e '
		.protocol == "leafos.orchestration.v0.3" and
		(.goal | type == "string") and
		(.actions | type == "array" and length > 0 and length <= 16) and
		(.actions | all(.id | test("^[a-z][a-z0-9_-]{0,48}$"))) and
		(.actions | all(.skill | IN("context.inspect","file.read","file.hash","check.run","report.write"))) and
		(.actions | all(.input | type == "object")) and
		(.actions | all(.depends_on | type == "array")) and
		([.actions[] | select(.skill == "file.read" or .skill == "file.hash") | .input.ref] | all(IN("readme","skeleton","wildcard"))) and
		([.actions[] | select(.skill == "check.run") | .input.check] | all(IN("leafctl-doctor","graph-tests","shell-syntax"))) and
		(.completion.required_actions | type == "array" and length > 0) and
		([.actions[].input | keys[]?] | all(IN("ref","check","message")))
	' "$plan" >/dev/null 2>&1 || return 1

	local duplicate
	duplicate="$(jq -r '.actions[].id' "$plan" | sort | uniq -d)"
	[[ -z "$duplicate" ]] || { brand_warn "orchestration: duplicate action id: $duplicate"; return 1; }

	local ids dep
	ids="$(jq -r '.actions[].id' "$plan")"
	while IFS= read -r dep; do
		[[ -z "$dep" ]] && continue
		grep -Fxq "$dep" <<< "$ids" || { brand_warn "orchestration: unknown dependency: $dep"; return 1; }
	done < <(jq -r '.actions[].depends_on[]?' "$plan")

	python3 - "$plan" <<'PY' >/dev/null 2>&1
import json
import sys
from collections import defaultdict, deque

with open(sys.argv[1], encoding="utf-8") as handle:
    plan = json.load(handle)
ids = {action["id"] for action in plan["actions"]}
indegree = {node: 0 for node in ids}
edges = defaultdict(list)
for action in plan["actions"]:
    for dep in action["depends_on"]:
        edges[dep].append(action["id"])
        indegree[action["id"]] += 1
queue = deque(node for node, degree in indegree.items() if degree == 0)
visited = 0
while queue:
    node = queue.popleft()
    visited += 1
    for child in edges[node]:
        indegree[child] -= 1
        if indegree[child] == 0:
            queue.append(child)
raise SystemExit(0 if visited == len(ids) else 1)
PY
}

_orch_state_init() {
	local plan="$1" state="$2"
	jq '[.actions[].id as $id | {key:$id,value:"pending"}] | from_entries' "$plan" > "$state"
}

_orch_state_set() {
	local state="$1" id="$2" status="$3" tmp
	tmp="$state.tmp.$$"
	jq --arg id "$id" --arg status "$status" '.[$id] = $status' "$state" > "$tmp" && mv "$tmp" "$state"
}

_orch_ready_action() {
	local plan="$1" state="$2"
	jq -r --slurpfile states "$state" '
		$states[0] as $s |
		.actions[] |
		select(($s[.id] // "pending") == "pending") |
		select([.depends_on[]? | ($s[.] // "missing") == "done"] | all) |
		.id
	' "$plan" | head -1
}

_orch_ref_path() {
	local run_dir="$1" ref="$2"
	jq -r --arg ref "$ref" '.inputs[$ref].snapshot // empty' "$run_dir/context.json"
}

_orch_dispatch_skill() {
	local run_dir="$1" action_id="$2" skill="$3" input="$4"
	local artifact="$run_dir/artifacts/$action_id"
	case "$skill" in
		context.inspect)
			jq . "$run_dir/context.json" > "$artifact.context.json"
			;;
		file.read)
			local ref path kind
			ref="$(jq -r '.ref // empty' <<< "$input")"
			path="$(_orch_ref_path "$run_dir" "$ref")"
			[[ -f "$path" ]] || return 1
			kind="$(jq -r --arg ref "$ref" '.inputs[$ref].kind' "$run_dir/context.json")"
			if [[ "$kind" == "text" ]]; then
				head -c "$LEAF_ORCHESTRATION_MAX_TEXT_BYTES" "$path" > "$artifact.txt"
			else
				jq -n --arg ref "$ref" --arg kind "$kind" '{ref:$ref,kind:$kind,read:false}' > "$artifact.json"
			fi
			;;
		file.hash)
			local hash_ref hash_path
			hash_ref="$(jq -r '.ref // empty' <<< "$input")"
			hash_path="$(_orch_ref_path "$run_dir" "$hash_ref")"
			[[ -f "$hash_path" ]] || return 1
			_orch_hash "$hash_path" > "$artifact.sha256"
			;;
		check.run)
			local check
			check="$(jq -r '.check // empty' <<< "$input")"
			case "$check" in
				leafctl-doctor) (cd "$_ORCH_ROOT" && bash bin/leafctl doctor) > "$artifact.log" 2>&1 ;;
				graph-tests)    (cd "$_ORCH_ROOT" && bash tests/graph.sh) > "$artifact.log" 2>&1 ;;
				shell-syntax)   (cd "$_ORCH_ROOT" && bash -n bin/leafctl) > "$artifact.log" 2>&1 ;;
				*) brand_warn "orchestration: check not allow-listed: $check"; return 1 ;;
			esac
			;;
		report.write)
			local message
			message="$(jq -r '.message // "orchestration complete"' <<< "$input")"
			{
				printf '# LeafOS 0.3 Orchestration Report\n\n'
				printf 'Protocol: leafos.orchestration.v0.3\n'
				printf 'Run: %s\n\n' "$run_dir"
				printf '## Result\n\n%s\n\n' "$message"
				printf '## Inputs\n\n'
				jq -r '.inputs | to_entries[] | "- \(.key): \(.value.kind), \(.value.bytes) bytes, sha256 \(.value.sha256)"' "$run_dir/context.json"
			} > "$run_dir/report.md"
			;;
		*) brand_warn "orchestration: unknown skill: $skill"; return 1 ;;
	esac
}

_orch_execute() {
	local run_dir="$1" plan="$2" state="$run_dir/execution.state.json"
	_orch_state_init "$plan" "$state"
	: > "$run_dir/execution.jsonl"
	local total; total="$(jq '.actions | length' "$plan")"
	local done=0
	while (( done < total )); do
		local action_id
		action_id="$(_orch_ready_action "$plan" "$state")"
		[[ -n "$action_id" ]] || { brand_warn "orchestration: action dependency deadlock"; return 1; }
		local action_json skill input started ended rc
		action_json="$(jq -c --arg id "$action_id" '.actions[] | select(.id == $id)' "$plan")"
		skill="$(jq -r '.skill' <<< "$action_json")"
		input="$(jq -c '.input' <<< "$action_json")"
		started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
		brand_say "execute $action_id [$skill]"
		if _orch_dispatch_skill "$run_dir" "$action_id" "$skill" "$input"; then
			rc=0
			_orch_state_set "$state" "$action_id" done
			done=$((done + 1))
		else
			rc=$?
			_orch_state_set "$state" "$action_id" failed
		fi
		ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
		jq -c -n --arg id "$action_id" --arg skill "$skill" --arg started "$started" --arg ended "$ended" --argjson rc "$rc" \
			'{id:$id,skill:$skill,status:(if $rc == 0 then "done" else "failed" end),started:$started,ended:$ended,exit_code:$rc}' \
			>> "$run_dir/execution.jsonl"
		(( rc == 0 )) || return "$rc"
	done
}

orchestration_run() {
	local readme="${1:-}" skeleton="${2:-}" wildcard="${3:-}"
	[[ -n "$readme" && -n "$skeleton" && -n "$wildcard" ]] || {
		brand_warn "usage: leafctl agent-orchestrate README SKELETON WILDCARD [--provider llamacpp] [--yes]"
		return 2
	}
	shift 3
	local execute=0 provider="$LEAF_ORCHESTRATION_PROVIDER"
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--yes) execute=1 ;;
			--provider=*) provider="${1#--provider=}" ;;
			--provider) [[ $# -ge 2 ]] || return 2; provider="$2"; shift ;;
			*) brand_warn "orchestration: unknown option: $1"; return 2 ;;
		esac
		shift
	done
	LEAF_ORCHESTRATION_PROVIDER="$provider"

	readme="$(_orch_abs_file "$readme")" || { brand_warn "readme input not found"; return 1; }
	skeleton="$(_orch_abs_file "$skeleton")" || { brand_warn "skeleton input not found"; return 1; }
	wildcard="$(_orch_abs_file "$wildcard")" || { brand_warn "wildcard input not found"; return 1; }
	command -v jq >/dev/null 2>&1 || { brand_warn "orchestration requires jq"; return 3; }
	command -v python3 >/dev/null 2>&1 || { brand_warn "orchestration requires python3"; return 3; }
	[[ -f "$LEAF_ORCHESTRATION_SCHEMA" ]] || { brand_warn "missing orchestration schema"; return 3; }

	local run_dir
	run_dir="$LEAF_ORCHESTRATION_RUNS_DIR/orchestration-$(date -u +%Y%m%dT%H%M%SZ)-$$"
	mkdir -p "$run_dir"
	_orch_snapshot_inputs "$run_dir" "$readme" "$skeleton" "$wildcard" || return 1
	_orch_build_prompt "$run_dir"
	_orch_model_plan "$run_dir" || {
		brand_warn "orchestration: model did not produce a plan; no action executed"
		return 2
	}
	orchestration_plan_validate "$run_dir/plan.json" || {
		brand_warn "orchestration: plan rejected; no action executed"
		return 1
	}
	cp "$LEAF_ORCHESTRATION_SCHEMA" "$run_dir/action.schema.json"
	brand_say "orchestration plan ready: $run_dir/plan.json"
	if (( execute == 0 )); then
		brand_say "plan-only mode: pass --yes to execute allow-listed skills"
		printf '%s\n' "$run_dir"
		return 0
	fi
	_orch_execute "$run_dir" "$run_dir/plan.json" || {
		brand_warn "orchestration: execution failed; see $run_dir/execution.jsonl"
		return 1
	}
	brand_ok "orchestration complete: $run_dir/report.md"
	printf '%s\n' "$run_dir"
}
