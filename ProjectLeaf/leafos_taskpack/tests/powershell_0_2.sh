#!/usr/bin/env bash
# PowerShell forwarding parity checks for the 0.2 CLI surface.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PS_CLI="$ROOT_DIR/bin/leafctl.ps1"
fail() { echo "PowerShell 0.2 parity FAILED: $*" >&2; exit 1; }

for command_name in agent-task agent-plan agent-route agent-validate agent-dry-run agent-run agent-report; do
    grep -q "$command_name" "$ROOT_DIR/bin/leafctl" \
        || fail "Bash CLI missing $command_name"
done

grep -q "\$bash" "$PS_CLI" || fail "PowerShell CLI has no Bash fallback"
grep -q "default" "$PS_CLI" || fail "PowerShell CLI has no forwarding default"
grep -q "agent-dry-run" "$PS_CLI" || fail "PowerShell CLI does not document agent forwarding"

pwsh_bin=""
if command -v pwsh >/dev/null 2>&1; then
    pwsh_bin="pwsh"
elif command -v powershell >/dev/null 2>&1; then
    pwsh_bin="powershell"
fi

if [[ -n "$pwsh_bin" ]]; then
    bash_help="$($ROOT_DIR/bin/leafctl help)"
    ps_help="$($pwsh_bin -NoProfile -File "$PS_CLI" --help)" \
        || fail "PowerShell help forwarding failed"
    for command_name in agent-task agent-plan agent-route agent-validate agent-dry-run agent-run agent-report; do
        grep -q "$command_name" <<< "$bash_help" || fail "Bash help missing $command_name"
        grep -q "$command_name" <<< "$ps_help" || fail "PowerShell help missing $command_name"
    done
    echo "PowerShell forwarding parity passed"
else
    echo "PowerShell forwarding parity static checks passed (runtime skipped: pwsh not installed)"
fi
