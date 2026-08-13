#!/usr/bin/env bash
# core/patch/apply.sh  --  Patch application (WO-007-C §4.2)
#
# patch_apply_file PATCH_FILE [ROOT_DIR] [--yes]
#
# ALWAYS re-runs patch_validate before applying.
# Apply requires --yes. Without it, preview is shown and the command exits 0.
# There is no code path that mutates the repo without a passing gate.
#
# Exit codes: 0=ok, 1=gate failed or no --yes, 3=prereq missing

set -uo pipefail

_AP_ROOT="${_AP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_AP_ROOT/core/brand/brand.sh"
source "$_AP_ROOT/core/patch/validate.sh"

# ---------------------------------------------------------------------------
# patch_apply_file PATCH_FILE [ROOT_DIR] [--yes]
# ---------------------------------------------------------------------------
patch_apply_file() {
	local patch="${1:-}"
	local root="${2:-$_AP_ROOT}"
	local confirm="${3:-}"

	[[ -f "$patch" ]] || { brand_warn "patch_apply_file: not found: $patch"; return 1; }

	# Gate: always validate first, even with --yes
	brand_header "patch gate: ${patch##*/}"
	if ! patch_validate "$patch" "$root"; then
		brand_warn "apply blocked: patch did not pass validation"
		return 1
	fi

	# Preview always shown
	printf '\n'
	patch_preview "$patch"
	printf '\n'

	if [[ "$confirm" != "--yes" ]]; then
		brand_say "dry-run complete. Pass --yes to apply."
		return 0
	fi

	# Apply
	brand_say "applying patch: ${patch##*/}"
	if git -C "$root" apply "$patch"; then
		brand_ok "patch applied: $patch"
		return 0
	else
		brand_warn "git apply failed after gate passed -- this is unexpected"
		return 1
	fi
}
