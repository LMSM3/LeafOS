#!/usr/bin/env bash
# core/providers/test.sh  --  Provider smoke tests (WO-007-C §2)
#
# Usage:
#   leaf_provider_test [PROVIDER] [--json]    6 checks, grepable [ok]/[fail]
#   leaf_provider_prompt PROMPT [--json]      single live call, print result
#
# Exit code: 0 only if every check passed. Any [fail] -> non-zero.
# --json: emit one JSON object instead of [ok]/[fail] lines (CI-friendly).

set -uo pipefail

_TEST_ROOT="${_TEST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_TEST_ROOT/core/brand/brand.sh"
source "$_TEST_ROOT/core/providers/providers.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_TEST_ROOT/runs}"

# ---------------------------------------------------------------------------
# leaf_provider_test [PROVIDER] [--json]
# ---------------------------------------------------------------------------
leaf_provider_test() {
	local provider="" json=0
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--json) json=1 ;;
			*)      provider="$1" ;;
		esac
		shift
	done
	[[ -n "$provider" ]] || provider="$LEAF_PROVIDER_MODE"

	local -a checks=() results=() msgs=()
	local pass=0 fail=0

	# -- Helper: record a check result -------------------------------------
	_check() {
		local label="$1" ok="$2" msg="${3:-}"
		checks+=("$label")
		results+=("$ok")
		msgs+=("$msg")
		if [[ "$ok" == "1" ]]; then
			(( pass++ )) || true
		else
			(( fail++ )) || true
		fi
	}

	# 1. Provider reachable ------------------------------------------------
	if [[ "$provider" == "mock" ]]; then
		_check "provider reachable" 1 "gated test adapter is enabled"
	elif [[ "$provider" == "ollama" ]]; then
		if _leaf_ollama_ping; then
			_check "provider reachable" 1 "$LEAF_OLLAMA_HOST"
		else
			_check "provider reachable" 0 "ollama not running -- start with: ollama serve"
		fi
	else
		_check "provider reachable" 1 "$provider (remote; reachability checked on call)"
	fi

	# 2. Model configured --------------------------------------------------
	local model_label
	case "$provider" in
		mock)      model_label="mock" ;;
		ollama)    model_label="$LEAF_OLLAMA_MODEL" ;;
		openai)    model_label="${LEAF_OPENAI_MODEL:-unset}" ;;
		anthropic) model_label="${LEAF_ANTHROPIC_MODEL:-unset}" ;;
		deepseek)  model_label="${LEAF_DEEPSEEK_MODEL:-unset}" ;;
		zai|glm)   model_label="${LEAF_ZAI_MODEL:-unset}" ;;
		llamacpp)  model_label="llamacpp:${LEAF_LLAMACPP_URL:-unset}" ;;
		*)         model_label="unknown" ;;
	esac
	if [[ "$model_label" == "unset" || "$model_label" == "unknown" ]]; then
		_check "model configured" 0 "model not set for provider: $provider"
	else
		_check "model configured" 1 "$model_label"
	fi

	# 3–6: Live call checks (skipped for offline providers) ----------------
	local tmp_task; tmp_task="$(mktemp /tmp/leaf_test_task_XXXXXX.md)"
	printf '# Provider test task\n\n## Steps\n1. write one run_step line\n' >"$tmp_task"
	local tmp_run; tmp_run="$(mktemp -d /tmp/leaf_test_run_XXXXXX)"

	# Call directly (not in subshell) so contract vars are set
	leaf_provider_call "$tmp_task" "$tmp_run" "$provider"
	local call_rc=$?

	rm -f "$tmp_task"

	# 3. Response non-empty ------------------------------------------------
	if [[ "${LEAF_PROVIDER_OK:-0}" == "1" && -s "${LEAF_PROVIDER_TEXT_FILE:-}" ]]; then
		_check "response non-empty" 1 "${LEAF_PROVIDER_BYTES:-0} bytes"
	else
		local err="${LEAF_PROVIDER_ERROR:-call_failed}"
		_check "response non-empty" 0 "error: $err"
	fi

	# 4. No markdown fence pollution (raw file should not have fences if
	#    the prompt was obeyed; this catches models that ignore instructions)
	if [[ "${LEAF_PROVIDER_OK:-0}" == "1" && -s "${LEAF_PROVIDER_TEXT_FILE:-}" ]]; then
		if grep -q '^```' "$LEAF_PROVIDER_TEXT_FILE" 2>/dev/null; then
			_check "no markdown fence pollution" 0 "response contains fence markers -- model ignored formatting rules"
		else
			_check "no markdown fence pollution" 1 ""
		fi
	else
		_check "no markdown fence pollution" 0 "skipped (no response)"
	fi

	# 5. Timeout respected -------------------------------------------------
	local ms="${LEAF_PROVIDER_MS:-0}"
	local limit_ms=$(( LEAF_AI_TIMEOUT_SEC * 1000 + 1000 ))  # +1s grace
	if (( ms <= limit_ms )); then
		_check "timeout respected" 1 "${ms}ms (limit: ${LEAF_AI_TIMEOUT_SEC}s)"
	else
		_check "timeout respected" 0 "${ms}ms exceeded ${LEAF_AI_TIMEOUT_SEC}s limit"
	fi

	# 6. Contract version present ------------------------------------------
	if [[ "${LEAF_PROVIDER_CONTRACT:-0}" == "1" ]]; then
		_check "contract version present" 1 "LEAF_PROVIDER_CONTRACT=1"
	else
		_check "contract version present" 0 "LEAF_PROVIDER_CONTRACT not set -- adapter bug"
	fi

	rm -rf "$tmp_run"

	# -- Output -----------------------------------------------------------
	if [[ $json -eq 1 ]]; then
		local json_checks="[]"
		local i
		for (( i=0; i<${#checks[@]}; i++ )); do
			json_checks="$(printf '%s' "$json_checks" | python3 -c '
import json, sys
arr = json.load(sys.stdin)
arr.append({"check": sys.argv[1], "ok": sys.argv[2] == "1", "msg": sys.argv[3]})
print(json.dumps(arr))
' "${checks[$i]}" "${results[$i]}" "${msgs[$i]}")"
		done
		python3 -c '
import json, sys
print(json.dumps({
    "provider": sys.argv[1],
    "pass": int(sys.argv[2]),
    "fail": int(sys.argv[3]),
    "checks": json.load(sys.stdin),
}))
' "$provider" "$pass" "$fail" <<< "$json_checks"
	else
		brand_header "provider test: $provider"
		for (( i=0; i<${#checks[@]}; i++ )); do
			if [[ "${results[$i]}" == "1" ]]; then
				printf '  [ok]   %s' "${checks[$i]}"
				[[ -n "${msgs[$i]}" ]] && printf '  (%s)' "${msgs[$i]}"
				printf '\n'
			else
				printf '  [fail] %s' "${checks[$i]}"
				[[ -n "${msgs[$i]}" ]] && printf '  -- %s' "${msgs[$i]}"
				printf '\n'
			fi
		done
		printf '\n'
		if [[ $fail -eq 0 ]]; then
			brand_ok "all $pass checks passed"
		else
			brand_warn "$fail of $(( pass + fail )) checks failed"
		fi
	fi

	[[ $fail -eq 0 ]]
}

# ---------------------------------------------------------------------------
# leaf_provider_prompt PROMPT [--json]
# Send a single raw prompt and display the result.
# ---------------------------------------------------------------------------
leaf_provider_prompt() {
	local prompt="" json=0
	while [[ $# -gt 0 ]]; do
		case "$1" in
			--json) json=1 ;;
			*)      prompt="$prompt $1" ;;
		esac
		shift
	done
	prompt="${prompt# }"
	[[ -n "$prompt" ]] || { brand_warn "leaf_provider_prompt: no prompt given"; return 1; }

	local tmp_task; tmp_task="$(mktemp /tmp/leaf_prompt_task_XXXXXX.md)"
	printf '# Direct prompt\n\n## Steps\n1. %s\n' "$prompt" >"$tmp_task"
	local tmp_run; tmp_run="$(mktemp -d /tmp/leaf_prompt_run_XXXXXX)"

	leaf_provider_call "$tmp_task" "$tmp_run" "$LEAF_PROVIDER_MODE"
	local rc=$?
	rm -f "$tmp_task"

	if [[ $rc -eq 0 && -s "${LEAF_PROVIDER_TEXT_FILE:-}" ]]; then
		if [[ $json -eq 1 ]]; then
			python3 -c "
import json, sys
text = sys.stdin.read()
print(json.dumps({'ok': True, 'provider': '${LEAF_PROVIDER_NAME:-}', 'model': '${LEAF_PROVIDER_MODEL:-}', 'ms': ${LEAF_PROVIDER_MS:-0}, 'bytes': ${LEAF_PROVIDER_BYTES:-0}, 'text': text}))" <"$LEAF_PROVIDER_TEXT_FILE"
		else
			cat "$LEAF_PROVIDER_TEXT_FILE"
		fi
	else
		local err="${LEAF_PROVIDER_ERROR:-unknown}"
		if [[ $json -eq 1 ]]; then
			printf '{"ok":false,"provider":"%s","error":"%s","ms":%s}\n' \
				"${LEAF_PROVIDER_NAME:-}" "$err" "${LEAF_PROVIDER_MS:-0}"
		else
			brand_warn "provider call failed: $err (${LEAF_PROVIDER_MS:-0}ms)"
		fi
	fi

	rm -rf "$tmp_run"
	return $rc
}
