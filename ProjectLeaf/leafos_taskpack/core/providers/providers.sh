#!/usr/bin/env bash
# core/providers/providers.sh  --  LeafOS provider routing layer, contract v1.
#
# CONTRACT V1 (WO-007-C §1): model text NEVER travels through a shell variable.
# It is written atomically to a file; callers read LEAF_PROVIDER_TEXT_FILE.
#
# Success env:
#   LEAF_PROVIDER_OK=1  NAME  MODEL  TEXT_FILE  BYTES  MS  CONTRACT=1
# Failure env:
#   LEAF_PROVIDER_OK=0  NAME  ERROR  MS  CONTRACT=1
#   LEAF_PROVIDER_ERROR in: timeout|not_running|bad_json|empty_response|refused|contract_error
#
# IMPORTANT: call leaf_provider_call DIRECTLY, never inside $() — env vars propagate
# to the caller only when not run in a subshell.

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/brand/brand.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/glyphs/glyphs.sh"
[[ -f "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/runtime/runtime.sh" ]] && \
	source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/runtime/runtime.sh"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROVIDER_CONFIG="${PROVIDER_CONFIG:-$LEAF_CONFIG_DIR/providers.conf}"
[[ -f "$PROVIDER_CONFIG" ]] && source "$PROVIDER_CONFIG"

LEAF_PROVIDER_MODE="${LEAF_PROVIDER_MODE:-off}"
LEAF_REQUIRE_REAL_PROVIDER="${LEAF_REQUIRE_REAL_PROVIDER:-0}"
LEAF_ENABLE_TEST_MOCK_PROVIDER="${LEAF_ENABLE_TEST_MOCK_PROVIDER:-0}"

# Routing policy (WO-007-C §6): per-task-type preferred provider
LEAF_BRAIN_PROVIDER="${LEAF_BRAIN_PROVIDER:-${LEAF_PROVIDER_MODE}}"
LEAF_CODER_PROVIDER="${LEAF_CODER_PROVIDER:-${LEAF_PROVIDER_MODE}}"
LEAF_REVIEW_PROVIDER="${LEAF_REVIEW_PROVIDER:-off}"

# Ollama local
LEAF_OLLAMA_HOST="${LEAF_OLLAMA_HOST:-http://127.0.0.1:11434}"
LEAF_OLLAMA_MODEL="${LEAF_OLLAMA_MODEL:-qwen3:0.6b}"

# Optional Z.AI remote advisory lane. A model must be selected explicitly;
# GLM-5.2 is not an active default for the local medium-MoE policy.
LEAF_ZAI_KEY_VAR="${LEAF_ZAI_KEY_VAR:-ZAI_API_KEY}"
LEAF_ZAI_MODEL="${LEAF_ZAI_MODEL:-}"
LEAF_ZAI_BASE_URL="${LEAF_ZAI_BASE_URL:-https://api.z.ai/api/paas/v4}"
LEAF_ZAI_CODING_BASE_URL="${LEAF_ZAI_CODING_BASE_URL:-https://api.z.ai/api/coding/paas/v4}"
LEAF_ZAI_REASONING_EFFORT="${LEAF_ZAI_REASONING_EFFORT:-medium}"
LEAF_ZAI_RESPONSE_FORMAT="${LEAF_ZAI_RESPONSE_FORMAT:-text}"

# Limits
# NOTE (WO-019 WP-2): LEAF_PROVIDER_MAX_TOKENS is the visible-output ceiling
# for a single provider call, not the reasoning budget. See
# config/runtime-profiles.json for the full context/reasoning/output budget
# doctrine (C = I + P + R + O + S). The default below matches the
# "continual" profile's max_output_tokens.
LEAF_PROVIDER_PROFILE="${LEAF_PROVIDER_PROFILE:-continual}"
LEAF_AI_TIMEOUT_SEC="${LEAF_AI_TIMEOUT_SEC:-120}"
LEAF_PROVIDER_TEMPERATURE="${LEAF_PROVIDER_TEMPERATURE:-0.2}"
LEAF_PROVIDER_MAX_TOKENS="${LEAF_PROVIDER_MAX_TOKENS:-8192}"
LEAF_LLAMACPP_URL="${LEAF_LLAMACPP_URL:-http://127.0.0.1:8080}"
LEAF_LLAMACPP_CHAT_URL="${LEAF_LLAMACPP_CHAT_URL:-${LEAF_LLAMACPP_URL}/v1/chat/completions}"
LEAF_LLAMACPP_MODEL="${LEAF_LLAMACPP_MODEL:-local-vulkan}"
LEAF_LLAMACPP_MAX_TOKENS="${LEAF_LLAMACPP_MAX_TOKENS:-512}"

# ---------------------------------------------------------------------------
# Exit-code constants (Appendix B: 0=ok 1=validation 2=provider 3=contract 4=usage)
# Guard against redefinition when providers.sh is sourced more than once
# (leafctl sources brain.sh + coder.sh which each source providers.sh).
# ---------------------------------------------------------------------------
[[ -v _EXIT_OK ]] || readonly _EXIT_OK=0
[[ -v _EXIT_VALIDATION ]] || readonly _EXIT_VALIDATION=1
[[ -v _EXIT_PROVIDER ]] || readonly _EXIT_PROVIDER=2
[[ -v _EXIT_CONTRACT ]] || readonly _EXIT_CONTRACT=3
[[ -v _EXIT_USAGE ]] || readonly _EXIT_USAGE=4

# ---------------------------------------------------------------------------
# Contract helpers
# ---------------------------------------------------------------------------
_leaf_contract_reset() {
	unset LEAF_PROVIDER_OK LEAF_PROVIDER_NAME LEAF_PROVIDER_MODEL \
		  LEAF_PROVIDER_TEXT_FILE LEAF_PROVIDER_BYTES LEAF_PROVIDER_MS \
		  LEAF_PROVIDER_ERROR LEAF_PROVIDER_CONTRACT
}

_leaf_contract_ok() {
	local name="$1" model="$2" text_file="$3" bytes="$4" ms="$5"
	export LEAF_PROVIDER_OK=1
	export LEAF_PROVIDER_NAME="$name"
	export LEAF_PROVIDER_MODEL="$model"
	export LEAF_PROVIDER_TEXT_FILE="$text_file"
	export LEAF_PROVIDER_BYTES="$bytes"
	export LEAF_PROVIDER_MS="$ms"
	export LEAF_PROVIDER_CONTRACT=1
}

_leaf_contract_fail() {
	local name="$1" error="$2" ms="$3"
	export LEAF_PROVIDER_OK=0
	export LEAF_PROVIDER_NAME="$name"
	export LEAF_PROVIDER_ERROR="$error"
	export LEAF_PROVIDER_MS="$ms"
	export LEAF_PROVIDER_CONTRACT=1
}

_leaf_ms_now() {
	date +%s%3N 2>/dev/null || printf '%s000' "$(date +%s)"
}

# ---------------------------------------------------------------------------
# leaf_provider_call TASK_FILE OUT_DIR [PROVIDER]
# Public API. Call DIRECTLY (not in subshell). Sets LEAF_PROVIDER_* env vars.
# ---------------------------------------------------------------------------
leaf_provider_call() {
	local task_file="$1"
	local out_dir="$2"
	local provider="${3:-${LEAF_PROVIDER_MODE}}"

	_leaf_contract_reset
	if [[ "$provider" == "mock" && "$LEAF_ENABLE_TEST_MOCK_PROVIDER" != "1" ]]; then
		_leaf_contract_fail "mock" "test_provider_disabled" "0"
		leaf_alert error "leaf_provider_call: mock is a test-only provider and is disabled"
		return $_EXIT_CONTRACT
	fi
	if [[ "$provider" == "off" ]]; then
		_leaf_contract_fail "off" "provider_disabled" "0"
		leaf_alert error "leaf_provider_call: provider lane is off"
		return $_EXIT_PROVIDER
	fi

	if [[ ! -f "$task_file" ]]; then
		_leaf_contract_fail "$provider" "contract_error" "0"
		leaf_alert error "leaf_provider_call: task file not found: $task_file"
		return $_EXIT_CONTRACT
	fi

	mkdir -p "$out_dir"
	local raw_file="$out_dir/response.raw.txt"

	printf '%s %s routing via %s\n' \
		"$(leaf_glyph leaf.flow)" "$(leaf_glyph leaf.micro)" "$provider" >&2

	case "$provider" in
		mock)      _leaf_adapter_mock      "$task_file" "$raw_file" ;;
		ollama)    _leaf_adapter_ollama    "$task_file" "$raw_file" ;;
		openai)    _leaf_adapter_openai    "$task_file" "$raw_file" ;;
		anthropic) _leaf_adapter_anthropic "$task_file" "$raw_file" ;;
		deepseek)  _leaf_adapter_deepseek  "$task_file" "$raw_file" ;;
		zai|glm)   _leaf_adapter_zai       "$task_file" "$raw_file" ;;
		llamacpp)  _leaf_adapter_llamacpp  "$task_file" "$raw_file" ;;
		*)
			_leaf_contract_fail "$provider" "contract_error" "0"
			leaf_alert error "leaf_provider_call: unknown provider: $provider"
			return $_EXIT_CONTRACT
			;;
	esac
}

# Compat shim — old callers that captured stdout still work
leaf_provider_route() {
	local task_file="${1:-}"
	local tmp_dir; tmp_dir="$(mktemp -d /tmp/leaf_route_XXXXXX)"
	leaf_provider_call "$task_file" "$tmp_dir" "$LEAF_PROVIDER_MODE"
	local rc=$?
	if [[ $rc -eq 0 && -f "${LEAF_PROVIDER_TEXT_FILE:-}" ]]; then
		cat "$LEAF_PROVIDER_TEXT_FILE"
	fi
	rm -rf "$tmp_dir"
	return $rc
}

# ---------------------------------------------------------------------------
# leaf_provider_status
# ---------------------------------------------------------------------------
leaf_provider_status() {
	leaf_glyph_load
	local mode="$LEAF_PROVIDER_MODE"
	printf '%s provider: %s\n' "$(leaf_glyph leaf.model)" "$mode"
	printf '  brain -> %s  |  coder -> %s  |  review -> %s\n' \
		"$LEAF_BRAIN_PROVIDER" "$LEAF_CODER_PROVIDER" "$LEAF_REVIEW_PROVIDER"
	case "$mode" in
		off)
			printf '  %s provider lane disabled; no synthetic response will be generated\n' "$(leaf_glyph leaf.warn)"
			;;
		mock)
			printf '  %s test-only mock adapter (enabled=%s)\n' "$(leaf_glyph leaf.warn)" "$LEAF_ENABLE_TEST_MOCK_PROVIDER"
			;;
		openai)
			_leaf_provider_key_check "$LEAF_OPENAI_KEY_VAR"
			printf '  %s model: %s\n' "$(leaf_glyph leaf.model.primary)" "$LEAF_OPENAI_MODEL"
			;;
		anthropic)
			_leaf_provider_key_check "$LEAF_ANTHROPIC_KEY_VAR"
			printf '  %s model: %s\n' "$(leaf_glyph leaf.model.primary)" "$LEAF_ANTHROPIC_MODEL"
			;;
		deepseek)
			_leaf_provider_key_check "$LEAF_DEEPSEEK_KEY_VAR"
			printf '  %s model: %s\n' "$(leaf_glyph leaf.model.primary)" "$LEAF_DEEPSEEK_MODEL"
			;;
		zai|glm)
			_leaf_provider_key_check "$LEAF_ZAI_KEY_VAR"
			printf '  %s model: %s\n' "$(leaf_glyph leaf.model.primary)" "$LEAF_ZAI_MODEL"
			printf '  %s lane: planner/reviewer advisory; CPU/local coder remains authority\n' "$(leaf_glyph leaf.lane)"
			;;
		llamacpp)
			printf '  %s endpoint: %s\n' "$(leaf_glyph leaf.lane)" "$LEAF_LLAMACPP_URL"
			;;
		ollama)
			_leaf_ollama_ping \
				&& printf '  %s running\n' "$(leaf_glyph leaf.pass)" \
				|| printf '  %s not reachable -- start with: ollama serve\n' "$(leaf_glyph leaf.warn)"
			printf '  %s endpoint: %s\n' "$(leaf_glyph leaf.lane)"          "$LEAF_OLLAMA_HOST"
			printf '  %s model:    %s\n' "$(leaf_glyph leaf.model.primary)" "$LEAF_OLLAMA_MODEL"
			;;
		*)
			leaf_alert warn "unknown provider mode: $mode"
			;;
	esac
}

_leaf_provider_key_check() {
	local var="$1" val="${!1:-}"
	if [[ -n "$val" ]]; then
		printf '  %s %s set\n' "$(leaf_glyph leaf.pass)" "$var"
	else
		leaf_alert warn "$var not set; routing will fail"
	fi
}

_leaf_task_section() {
	local task_file="$1" section="$2"
	awk -v section="$section" '
		$0 == "## " section { in_section=1; next }
		in_section && /^## / { exit }
		in_section { print }
	' "$task_file"
}

# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------
_leaf_ollama_ping() {
	curl -fsSL --max-time 2 "${LEAF_OLLAMA_HOST}/api/version" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Adapters — signature: (task_file, out_file)
# Each adapter: writes raw bytes atomically (tmp+mv), then calls contract helper.
# ---------------------------------------------------------------------------

_leaf_adapter_mock() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	local now title scope steps_raw

	now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
	title="$(_leaf_task_section "$task_file" Title 2>/dev/null | sed -n '/[^[:space:]]/{s/^[[:space:]]*//;p;q;}')"
	[[ -n "$title" ]] || title="$(basename "$task_file" .md)"
	scope="$(_leaf_task_section "$task_file" Scope 2>/dev/null | sed -n 's/^[[:space:]]*-[[:space:]]*//p' | head -5 | tr '\n' ';' | sed 's/;$//')"
	[[ -n "$scope" ]] || scope="general task"
	steps_raw="$(_leaf_task_section "$task_file" Steps 2>/dev/null | sed -nE 's/^[[:space:]]*[0-9]+\.[[:space:]]*//p' | head -8)"

	local plan_body=""
	if [[ -n "$steps_raw" ]]; then
		while IFS= read -r line; do
			local step_desc; step_desc="$(printf '%s' "$line" | sed 's/^[0-9]*\.[[:space:]]*//')"
			[[ -z "$step_desc" ]] && continue
			local cmd; cmd="$(_leaf_mock_step_to_cmd "$step_desc")"
			plan_body+="run_step $cmd"$'\n'
		done <<< "$steps_raw"
	fi
	[[ -n "$plan_body" ]] || plan_body='run_step "$ROOT_DIR/bin/leafctl" doctor
run_step "$ROOT_DIR/bin/leafctl" status
run_step "$ROOT_DIR/tests/smoke.sh"'

	local tmp; tmp="${out_file}.tmp.$$"
	{
		printf '#!/usr/bin/env bash\n'
		printf '# LEAFOS_AGENT_PLAN=1\n'
		printf '# LEAFOS_AGENT_PLAN_VERSION=0.2.0\n'
		printf '# Generated:  %s\n# Task:       %s\n# Title:      %s\n# Scope:      %s\n# Provider:   mock (offline)\n' \
			"$now" "$task_file" "$title" "$scope"
		printf '\nset -euo pipefail\n\n'
		printf 'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n\n'
		printf '%s\n' 'run_step() { printf '"'"'agent-step: %s\n'"'"' "$*"; "$@"; }'
		printf '\n'
		printf '%s\n' "$plan_body"
	} >"$tmp"
	mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "mock" "mock" "$out_file" "$bytes" "$(( $(_leaf_ms_now) - t0 ))"
}

_leaf_mock_step_to_cmd() {
	local desc="${1,,}"
	local quoted
	case "$desc" in
		*doctor*|*check*layout*) printf '"%s/bin/leafctl" doctor'  "$ROOT_DIR" ;;
		*status*)                printf '"%s/bin/leafctl" status'  "$ROOT_DIR" ;;
		*test*|*smoke*)          printf '"%s/tests/smoke.sh"'      "$ROOT_DIR" ;;
		*version*)               printf '"%s/bin/leafctl" versions' "$ROOT_DIR" ;;
		*platform*)              printf '"%s/bin/leafctl" platform' "$ROOT_DIR" ;;
		*)
			printf -v quoted '%q' "$1"
			printf 'printf "step: %%s\\n" %s' "$quoted"
			;;
	esac
}

_leaf_adapter_requires_key() {
	local provider="$1" key_var="$2"
	if [[ -z "${!key_var:-}" ]]; then
		leaf_alert error "$provider requires $key_var to be set"
		leaf_alert warn  "configure a real provider or set the lane to off"
		return 1
	fi
}

_leaf_adapter_ollama() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"

	if ! _leaf_ollama_ping; then
		_leaf_contract_fail "ollama" "not_running" "$(( $(_leaf_ms_now) - t0 ))"
		leaf_alert error "ollama not reachable at ${LEAF_OLLAMA_HOST} -- run: ollama serve"
		return $_EXIT_PROVIDER
	fi

	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local payload; payload="$(python3 -c "
import json, sys
prompt = sys.stdin.read()
print(json.dumps({'model': '${LEAF_OLLAMA_MODEL}', 'temperature': ${LEAF_PROVIDER_TEMPERATURE}, 'stream': False, 'messages': [{'role': 'user', 'content': prompt}]}))" <<< "$prompt")"

	local tmp; tmp="${out_file}.tmp.$$"
	local curl_out; curl_out="$(mktemp /tmp/leaf_curl_XXXXXX)"
	local http_rc=0
	curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" \
		"${LEAF_OLLAMA_HOST}/v1/chat/completions" \
		-H 'Content-Type: application/json' \
		-d "$payload" >"$curl_out" 2>&1 || http_rc=$?

	local elapsed; elapsed="$(( $(_leaf_ms_now) - t0 ))"

	if [[ $http_rc -ne 0 ]]; then
		rm -f "$curl_out"
		local err="refused"
		(( elapsed >= LEAF_AI_TIMEOUT_SEC * 1000 )) && err="timeout"
		_leaf_contract_fail "ollama" "$err" "$elapsed"
		return $_EXIT_PROVIDER
	fi

	local text
	if ! text="$(python3 -c "
import json, sys
try:
	d = json.load(sys.stdin)
	t = d['choices'][0]['message']['content']
	if not t: sys.exit(2)
	print(t, end='')
except Exception as e:
	sys.stderr.write(str(e)+'\n'); sys.exit(1)
" <"$curl_out" 2>/dev/null)"; then
		local ec=$?
		rm -f "$curl_out"
		[[ $ec -eq 2 ]] \
			&& _leaf_contract_fail "ollama" "empty_response" "$elapsed" \
			|| _leaf_contract_fail "ollama" "bad_json" "$elapsed"
		return $_EXIT_PROVIDER
	fi
	rm -f "$curl_out"

	# Write raw atomically — no stripping; raw.txt stays raw forever
	printf '%s' "$text" >"$tmp"
	mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "ollama" "$LEAF_OLLAMA_MODEL" "$out_file" "$bytes" "$elapsed"
}

_leaf_adapter_openai() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	_leaf_adapter_requires_key openai "$LEAF_OPENAI_KEY_VAR" || {
		_leaf_contract_fail "openai" "contract_error" "0"; return $_EXIT_CONTRACT; }
	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local payload; payload="$(printf '{"model":"%s","temperature":%s,"max_tokens":%s,"messages":[{"role":"user","content":%s}]}' \
		"$LEAF_OPENAI_MODEL" "$LEAF_PROVIDER_TEMPERATURE" "$LEAF_PROVIDER_MAX_TOKENS" \
		"$(printf '%s' "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"
	local tmp; tmp="${out_file}.tmp.$$"
	local resp; resp="$(curl -fsSL https://api.openai.com/v1/chat/completions \
		-H "Authorization: Bearer ${!LEAF_OPENAI_KEY_VAR}" \
		-H "Content-Type: application/json" -d "$payload" 2>&1)" \
		|| { _leaf_contract_fail "openai" "refused" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	local text; text="$(printf '%s' "$resp" | python3 -c \
		'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"],end="")' 2>/dev/null)" \
		|| { _leaf_contract_fail "openai" "bad_json" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	printf '%s' "$text" >"$tmp"; mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "openai" "$LEAF_OPENAI_MODEL" "$out_file" "$bytes" "$(( $(_leaf_ms_now)-t0 ))"
}

_leaf_adapter_anthropic() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	_leaf_adapter_requires_key anthropic "$LEAF_ANTHROPIC_KEY_VAR" || {
		_leaf_contract_fail "anthropic" "contract_error" "0"; return $_EXIT_CONTRACT; }
	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local payload; payload="$(printf '{"model":"%s","max_tokens":%s,"messages":[{"role":"user","content":%s}]}' \
		"$LEAF_ANTHROPIC_MODEL" "$LEAF_PROVIDER_MAX_TOKENS" \
		"$(printf '%s' "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"
	local tmp; tmp="${out_file}.tmp.$$"
	local resp; resp="$(curl -fsSL https://api.anthropic.com/v1/messages \
		-H "x-api-key: ${!LEAF_ANTHROPIC_KEY_VAR}" -H "anthropic-version: 2023-06-01" \
		-H "Content-Type: application/json" -d "$payload" 2>&1)" \
		|| { _leaf_contract_fail "anthropic" "refused" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	local text; text="$(printf '%s' "$resp" | python3 -c \
		'import json,sys; print(json.load(sys.stdin)["content"][0]["text"],end="")' 2>/dev/null)" \
		|| { _leaf_contract_fail "anthropic" "bad_json" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	printf '%s' "$text" >"$tmp"; mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "anthropic" "$LEAF_ANTHROPIC_MODEL" "$out_file" "$bytes" "$(( $(_leaf_ms_now)-t0 ))"
}

_leaf_adapter_deepseek() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	_leaf_adapter_requires_key deepseek "$LEAF_DEEPSEEK_KEY_VAR" || {
		_leaf_contract_fail "deepseek" "contract_error" "0"; return $_EXIT_CONTRACT; }
	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local payload; payload="$(printf '{"model":"%s","temperature":%s,"max_tokens":%s,"messages":[{"role":"user","content":%s}]}' \
		"$LEAF_DEEPSEEK_MODEL" "$LEAF_PROVIDER_TEMPERATURE" "$LEAF_PROVIDER_MAX_TOKENS" \
		"$(printf '%s' "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')")"
	local tmp; tmp="${out_file}.tmp.$$"
	local resp; resp="$(curl -fsSL https://api.deepseek.com/v1/chat/completions \
		-H "Authorization: Bearer ${!LEAF_DEEPSEEK_KEY_VAR}" \
		-H "Content-Type: application/json" -d "$payload" 2>&1)" \
		|| { _leaf_contract_fail "deepseek" "refused" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	local text; text="$(printf '%s' "$resp" | python3 -c \
		'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"],end="")' 2>/dev/null)" \
		|| { _leaf_contract_fail "deepseek" "bad_json" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	printf '%s' "$text" >"$tmp"; mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "deepseek" "$LEAF_DEEPSEEK_MODEL" "$out_file" "$bytes" "$(( $(_leaf_ms_now)-t0 ))"
}

_leaf_adapter_zai() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	_leaf_adapter_requires_key zai "$LEAF_ZAI_KEY_VAR" || {
		_leaf_contract_fail "zai" "contract_error" "0"; return $_EXIT_CONTRACT; }
	if [[ -z "$LEAF_ZAI_MODEL" ]]; then
		_leaf_contract_fail "zai" "contract_error" "0"
		leaf_alert error "zai adapter requires an explicit LEAF_ZAI_MODEL; GLM-5.2 is deprecated"
		return $_EXIT_CONTRACT
	fi

	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local endpoint="${LEAF_ZAI_BASE_URL%/}/chat/completions"
	local payload
	payload="$(printf '%s' "$prompt" | env \
		LEAF_ZAI_MODEL="$LEAF_ZAI_MODEL" \
		LEAF_PROVIDER_TEMPERATURE="$LEAF_PROVIDER_TEMPERATURE" \
		LEAF_PROVIDER_MAX_TOKENS="$LEAF_PROVIDER_MAX_TOKENS" \
		LEAF_ZAI_REASONING_EFFORT="$LEAF_ZAI_REASONING_EFFORT" \
		LEAF_ZAI_RESPONSE_FORMAT="$LEAF_ZAI_RESPONSE_FORMAT" \
		LEAF_ZAI_REQUEST_ID="${LEAF_ZAI_REQUEST_ID:-}" \
		python3 -c '
import json, os, sys
body = {
	"model": os.environ["LEAF_ZAI_MODEL"],
	"temperature": float(os.environ["LEAF_PROVIDER_TEMPERATURE"]),
	"max_tokens": int(os.environ["LEAF_PROVIDER_MAX_TOKENS"]),
	"messages": [{"role": "user", "content": sys.stdin.read()}],
}
reasoning = os.environ.get("LEAF_ZAI_REASONING_EFFORT", "").strip()
if reasoning:
	body["reasoning_effort"] = reasoning
if os.environ.get("LEAF_ZAI_RESPONSE_FORMAT", "text") == "json_object":
	body["response_format"] = {"type": "json_object"}
request_id = os.environ.get("LEAF_ZAI_REQUEST_ID", "").strip()
if request_id:
	body["request_id"] = request_id
print(json.dumps(body))
')" || {
		_leaf_contract_fail "zai" "contract_error" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_CONTRACT; }

	local tmp; tmp="${out_file}.tmp.$$"
	local curl_out; curl_out="$(mktemp /tmp/leaf_zai_curl_XXXXXX)"
	local http_rc=0
	curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" "$endpoint" \
		-H "Authorization: Bearer ${!LEAF_ZAI_KEY_VAR}" \
		-H "Content-Type: application/json" -d "$payload" >"$curl_out" 2>&1 || http_rc=$?
	local elapsed; elapsed="$(( $(_leaf_ms_now) - t0 ))"
	if [[ $http_rc -ne 0 ]]; then
		rm -f "$curl_out"
		local err="refused"
		(( elapsed >= LEAF_AI_TIMEOUT_SEC * 1000 )) && err="timeout"
		_leaf_contract_fail "zai" "$err" "$elapsed"
		return $_EXIT_PROVIDER
	fi

	local text
	if ! text="$(python3 -c '
import json, sys
try:
	text = json.load(sys.stdin)["choices"][0]["message"]["content"]
	if not text:
		sys.exit(2)
	print(text, end="")
except Exception:
	sys.exit(1)
	' <"$curl_out")"; then
		local parse_rc=$?
		rm -f "$curl_out"
		[[ $parse_rc -eq 2 ]] \
			&& _leaf_contract_fail "zai" "empty_response" "$elapsed" \
			|| _leaf_contract_fail "zai" "bad_json" "$elapsed"
		return $_EXIT_PROVIDER
	fi
	rm -f "$curl_out"
	printf '%s' "$text" >"$tmp"
	mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "zai" "$LEAF_ZAI_MODEL" "$out_file" "$bytes" "$elapsed"
}

_leaf_adapter_llamacpp() {
	local task_file="$1" out_file="$2"
	local t0; t0="$(_leaf_ms_now)"
	local prompt; prompt="$(_leaf_build_prompt "$task_file")"
	local payload; payload="$(printf '%s' "$prompt" | python3 -c '
import json, sys
prompt = sys.stdin.read()
print(json.dumps({
    "model": sys.argv[1],
    "messages": [{"role": "user", "content": prompt}],
    "temperature": float(sys.argv[2]),
    "max_tokens": int(sys.argv[3]),
    "stream": False,
    "stop": ["```"],
}, separators=(",", ":")))
' "$LEAF_LLAMACPP_MODEL" "$LEAF_PROVIDER_TEMPERATURE" "$LEAF_LLAMACPP_MAX_TOKENS")" \
		|| { _leaf_contract_fail "llamacpp" "contract_error" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_CONTRACT; }
	local tmp; tmp="${out_file}.tmp.$$"
	local resp; resp="$(curl -fsSL --max-time "$LEAF_AI_TIMEOUT_SEC" "$LEAF_LLAMACPP_CHAT_URL" \
		-H "Content-Type: application/json" -d "$payload" 2>&1)" \
		|| { _leaf_contract_fail "llamacpp" "refused" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	local text; text="$(printf '%s' "$resp" | python3 -c \
		'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"],end="")' 2>/dev/null)" \
		|| { _leaf_contract_fail "llamacpp" "bad_json" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	[[ -n "$text" ]] \
		|| { _leaf_contract_fail "llamacpp" "empty_response" "$(( $(_leaf_ms_now)-t0 ))"; return $_EXIT_PROVIDER; }
	printf '%s' "$text" >"$tmp"; mv "$tmp" "$out_file"
	local bytes; bytes="$(wc -c < "$out_file")"
	_leaf_contract_ok "llamacpp" "$LEAF_LLAMACPP_MODEL" "$out_file" "$bytes" "$(( $(_leaf_ms_now)-t0 ))"
}

# ---------------------------------------------------------------------------
# _leaf_build_prompt TASK_FILE  →  stdout
# ---------------------------------------------------------------------------
_leaf_build_prompt() {
	local task_file="$1"
	if declare -F leaf_runtime_prompt_preamble >/dev/null; then
		leaf_runtime_prompt_preamble
	fi
	printf 'You are an agentic coding assistant for LeafOS.\nThis is an internal planner call. Persona metadata may inform priorities, but this call must still output ONLY a bash script that is a valid LeafOS agent plan.\n\nRules:\n- First line: #!/usr/bin/env bash\n- Second line: # LEAFOS_AGENT_PLAN=1\n- Use run_step() to wrap each command.\n- Do not use sudo, rm -rf, mkfs, dd, shutdown, reboot, or curl | sh.\n- Keep the plan minimal and auditable.\n- Output only the script. No explanation.\n\nTask file:\n'
	cat "$task_file"
}
