#!/usr/bin/env bash
# WO-019 019-A / Gate G2 equivalence test.
#
# Proves that the Bash-facing resolver (core/runtime/profile_resolver.py,
# invoked directly the same way chat-local.sh does) and the PowerShell
# wrapper (bin/Resolve-RuntimeProfile.ps1) produce byte-equivalent canonical
# JSON manifests for the same profile/provider/model configuration.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKPACK_ROOT="$(cd "$HERE/.." && pwd)"
RESOLVER="$TASKPACK_ROOT/core/runtime/profile_resolver.py"
PROFILES_FILE="$TASKPACK_ROOT/config/runtime-profiles.json"
PS_WRAPPER="$TASKPACK_ROOT/bin/Resolve-RuntimeProfile.ps1"

fail() { echo "runtime_profile_manifest test FAILED: $*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || fail "python3 not available"
[[ -f "$RESOLVER" ]] || fail "missing resolver: $RESOLVER"
[[ -f "$PROFILES_FILE" ]] || fail "missing profiles file: $PROFILES_FILE"
[[ -f "$PS_WRAPPER" ]] || fail "missing PowerShell wrapper: $PS_WRAPPER"

PROFILE="continual"
PROVIDER="llama.cpp"
MODEL="test-model-id"

bash_output="$(python3 "$RESOLVER" --profiles-file "$PROFILES_FILE" --profile "$PROFILE" --provider "$PROVIDER" --model "$MODEL")"

printf '%s' "$bash_output" | grep -q '"profile":"continual"' \
  || fail "resolver manifest missing expected profile field: $bash_output"
printf '%s' "$bash_output" | grep -q '"context_limit":65536' \
  || fail "resolver manifest missing expected context_limit: $bash_output"

pwsh_bin="$(command -v pwsh || true)"
if [[ -z "$pwsh_bin" ]]; then
  echo "runtime_profile_manifest test SKIPPED: pwsh not installed; Bash-side manifest validated only." >&2
  echo "bash manifest: $bash_output"
  exit 0
fi

ps_output="$("$pwsh_bin" -NoProfile -File "$PS_WRAPPER" -Profile "$PROFILE" -Provider "$PROVIDER" -Model "$MODEL")"

if [[ "$bash_output" != "$ps_output" ]]; then
  fail "Bash and PowerShell manifests are not byte-equivalent:
  bash: $bash_output
  pwsh: $ps_output"
fi

echo "runtime_profile_manifest test PASSED: Bash and PowerShell manifests byte-equivalent."
echo "manifest: $bash_output"
