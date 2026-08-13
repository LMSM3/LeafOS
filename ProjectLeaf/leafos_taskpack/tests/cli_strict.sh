#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEAFCTL="$ROOT_DIR/bin/leafctl"

echo "[cli-strict] syntax check bin/leafctl"
bash -n "$LEAFCTL"

echo "[cli-strict] ensure leafctl can source all modules and answer help"
output_help=$("$LEAFCTL" help)
[[ "$output_help" == *"LeafOS"* ]]

echo "[cli-strict] ensure leafctl status emits JSON"
output_status=$("$LEAFCTL" status --json)
[[ "$output_status" == *"leafos"* ]]

echo "[cli-strict] capability gate: allowed request returns ticket"
output_allowed=$("$LEAFCTL" bloom capability input.append \
	--actor cli.strict.test \
	--reason 'sourcing smoke test' \
	--json)
[[ "$output_allowed" == *"\"allowed\":true"* ]]
[[ "$output_allowed" == *"leafos.capability_ticket.v1"* ]]

echo "[cli-strict] capability gate: denied request returns no-ticket"
set +e
output_denied=$("$LEAFCTL" bloom capability mutation.direct \
	--actor cli.strict.test \
	--reason 'sourcing smoke test' \
	--json)
denied_exit=$?
set -e
# Some pipelines return non-zero on denial; either is acceptable as long as the
# JSON clearly records the denial.
[[ "$output_denied" == *"\"allowed\":false"* ]]

echo "[cli-strict] all cli sourcing and capability checks passed"
