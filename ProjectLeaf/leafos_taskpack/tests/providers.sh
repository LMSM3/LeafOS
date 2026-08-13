#!/usr/bin/env bash
# Tests for the LeafOS provider routing layer.
set -euo pipefail
export LEAF_ENABLE_TEST_MOCK_PROVIDER=1
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/core/providers/providers.sh"
source "$ROOT_DIR/core/providers/test.sh"

fail() { echo "provider test FAILED: $*" >&2; exit 1; }

TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"; rm -f "$ROOT_DIR/tasks/provider-test-task.md" "$ROOT_DIR/tasks/provider-test-task.provider-gen.plan.sh"' EXIT

# --- mock adapter: generates a valid agent plan from a task file ------------

cat > "$TMPDIR_TEST/test-task.md" <<'TASK'
## Title
Run smoke checks

## Scope
- verify project layout
- run smoke tests

## Steps
1. Check doctor status
2. Run smoke tests
3. Print versions
TASK

LEAF_PROVIDER_MODE=mock
plan_out="$(leaf_provider_route "$TMPDIR_TEST/test-task.md")"

grep -q '^# LEAFOS_AGENT_PLAN=1' <<< "$plan_out" \
	|| fail "mock plan missing LEAFOS_AGENT_PLAN marker"
grep -q '^#!/usr/bin/env bash' <<< "$plan_out" \
	|| fail "mock plan missing shebang"
grep -q 'run_step' <<< "$plan_out" \
	|| fail "mock plan has no run_step commands"
grep -q 'Provider:   mock' <<< "$plan_out" \
	|| fail "mock plan missing provider tag"

if LEAF_ENABLE_TEST_MOCK_PROVIDER=0 leaf_provider_call "$TMPDIR_TEST/test-task.md" "$TMPDIR_TEST/mock-rejected" mock >/dev/null 2>&1; then
	fail "mock provider should be rejected without the test gate"
fi

# --- mock plan passes validation via agent_plan_generate -------------------

source "$ROOT_DIR/core/agent/agent.sh"

# Write task to tasks/ so agent_plan_generate can find it.
cp "$TMPDIR_TEST/test-task.md" "$ROOT_DIR/tasks/provider-test-task.md"

plan_path="$(agent_plan_generate "$ROOT_DIR/tasks/provider-test-task.md" "provider-gen")"
[[ -f "$plan_path" ]]        || fail "agent_plan_generate did not create plan file"
[[ -x "$plan_path" ]]        || fail "plan file is not executable"
bash -n "$plan_path"         || fail "plan file has syntax errors"
agent_plan_validate "$plan_path" >/dev/null || fail "generated plan failed validation"

# --- overwrite protection ---------------------------------------------------
if agent_plan_generate "$ROOT_DIR/tasks/provider-test-task.md" "provider-gen" 2>/dev/null; then
	fail "second agent_plan_generate should refuse to overwrite"
fi

# --- dry-run produces output ------------------------------------------------
agent_plan_dry_run "$plan_path" | grep -q 'would run' \
	|| fail "dry-run output missing 'would run'"

# --- provider-status mock does not error ------------------------------------
LEAF_PROVIDER_MODE=mock leaf_provider_status >/dev/null
_mock_summary="$(LEAF_PROVIDER_MODE=mock leaf_provider_test mock --json)"
python3 -c 'import json,sys; data=json.load(sys.stdin); assert data["pass"] == 6; assert data["fail"] == 0; assert len(data["checks"]) == 6' \
	<<< "$_mock_summary" || fail "provider JSON summary lost check details"

# --- API adapter stubs refuse without keys ----------------------------------
_stub_out="$(mktemp)"
LEAF_PROVIDER_MODE=openai OPENAI_API_KEY='' \
	leaf_provider_route "$TMPDIR_TEST/test-task.md" >"$_stub_out" 2>&1 || true
grep -q 'OPENAI_API_KEY' "$_stub_out" \
	|| fail "openai stub should report missing key"
LEAF_PROVIDER_MODE=zai ZAI_API_KEY='' \
	leaf_provider_route "$TMPDIR_TEST/test-task.md" >"$_stub_out" 2>&1 || true
grep -q 'ZAI_API_KEY' "$_stub_out" \
	|| fail "zai stub should report missing key"
LEAF_ZAI_KEY_VAR=LEAF_TEST_ZAI_KEY LEAF_TEST_ZAI_KEY=stub-secret LEAF_ZAI_MODEL='' \
	leaf_provider_call "$TMPDIR_TEST/test-task.md" "$TMPDIR_TEST/zai-unselected" zai >"$_stub_out" 2>&1 || true
grep -q 'requires an explicit LEAF_ZAI_MODEL' "$_stub_out" \
	|| fail "zai adapter should fail closed when no model is explicitly selected"
rm -f "$_stub_out"

# --- Z.AI adapter contract: local curl stub, no network or real key --------
_zai_request="$TMPDIR_TEST/zai-request.json"
_zai_endpoint="$TMPDIR_TEST/zai-endpoint.txt"
curl() {
	local arg payload="" endpoint=""
	while [[ $# -gt 0 ]]; do
		case "$1" in
			-d) payload="$2"; shift 2 ;;
			http://*|https://*) endpoint="$1"; shift ;;
			*) shift ;;
		esac
	done
	printf '%s' "$payload" >"$_zai_request"
	printf '%s' "$endpoint" >"$_zai_endpoint"
	printf '%s' '{"choices":[{"message":{"content":"#!/usr/bin/env bash\n# LEAFOS_AGENT_PLAN=1\nrun_step echo zai"}}]}'
}
LEAF_ZAI_KEY_VAR=LEAF_TEST_ZAI_KEY LEAF_TEST_ZAI_KEY=stub-secret \
	LEAF_ZAI_BASE_URL=http://leafos-zai-stub/v4 LEAF_ZAI_MODEL=zai-contract-fixture \
	LEAF_ZAI_REASONING_EFFORT=medium LEAF_ZAI_RESPONSE_FORMAT=text \
	LEAF_PROVIDER_MAX_TOKENS=12000 \
	leaf_provider_call "$TMPDIR_TEST/test-task.md" "$TMPDIR_TEST/zai-out" zai
[[ "${LEAF_PROVIDER_OK:-0}" == 1 ]] || fail "zai adapter did not set success contract"
[[ "${LEAF_PROVIDER_NAME:-}" == zai ]] || fail "zai adapter reported wrong name"
[[ "${LEAF_PROVIDER_MODEL:-}" == zai-contract-fixture ]] || fail "zai adapter reported wrong model"
[[ -s "${LEAF_PROVIDER_TEXT_FILE:-}" ]] || fail "zai adapter response file missing"
grep -q 'LEAFOS_AGENT_PLAN=1' "$LEAF_PROVIDER_TEXT_FILE" \
	|| fail "zai adapter did not persist raw response"
[[ "$(cat "$_zai_endpoint")" == 'http://leafos-zai-stub/v4/chat/completions' ]] \
	|| fail "zai adapter used wrong endpoint"
python3 - "$_zai_request" <<'PY' || fail "zai adapter request contract invalid"
import json, sys
request = json.load(open(sys.argv[1], encoding="utf-8"))
assert request["model"] == "zai-contract-fixture"
assert request["max_tokens"] == 12000
assert request["reasoning_effort"] == "medium"
assert request["messages"][0]["role"] == "user"
assert "response_format" not in request
PY
unset -f curl

# --- llama.cpp adapter contract: OpenAI chat route and bounded local output --
_llama_request="$TMPDIR_TEST/llama-request.json"
_llama_endpoint="$TMPDIR_TEST/llama-endpoint.txt"
curl() {
	local arg payload="" endpoint=""
	while [[ $# -gt 0 ]]; do
		case "$1" in
			-d) payload="$2"; shift 2 ;;
			http://*|https://*) endpoint="$1"; shift ;;
			*) shift ;;
		esac
	done
	printf '%s' "$payload" >"$_llama_request"
	printf '%s' "$endpoint" >"$_llama_endpoint"
	printf '%s' '{"choices":[{"message":{"content":"#!/usr/bin/env bash\n# LEAFOS_AGENT_PLAN=1\nrun_step echo llama"}}]}'
}
LEAF_LLAMACPP_CHAT_URL=http://leafos-llama-stub/v1/chat/completions \
	LEAF_LLAMACPP_MODEL=local-test LEAF_LLAMACPP_MAX_TOKENS=512 \
	leaf_provider_call "$TMPDIR_TEST/test-task.md" "$TMPDIR_TEST/llama-out" llamacpp
[[ "${LEAF_PROVIDER_OK:-0}" == 1 ]] || fail "llama.cpp adapter did not set success contract"
[[ "${LEAF_PROVIDER_MODEL:-}" == local-test ]] || fail "llama.cpp adapter reported wrong model"
[[ "$(cat "$_llama_endpoint")" == 'http://leafos-llama-stub/v1/chat/completions' ]] \
	|| fail "llama.cpp adapter used the raw completion endpoint"
python3 - "$_llama_request" <<'PY' || fail "llama.cpp adapter request contract invalid"
import json, sys
request = json.load(open(sys.argv[1], encoding="utf-8"))
assert request["model"] == "local-test"
assert request["max_tokens"] == 512
assert request["messages"][0]["role"] == "user"
assert request["stream"] is False
PY
unset -f curl

echo "provider tests passed"
