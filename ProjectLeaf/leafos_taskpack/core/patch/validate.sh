#!/usr/bin/env bash
# core/patch/validate.sh  --  Patch gate (WO-007-C §4)
#
# patch_validate PATCH_FILE [ROOT_DIR]
#
# Checks (all must pass; first failure exits with code 1):
#   1.  Non-empty
#   2.  Looks like unified diff (--- / +++ headers)
#   3.  git apply --check passes
#   4.  No paths escaping ROOT_DIR (after normalization)
#   5.  Does not touch .git/
#   6.  Does not touch secret / credential files (deny-list)
#   7.  No binary blobs
#   8.  No +x mode change or symlink addition
#   9.  Changed lines <= LEAF_PATCH_MAX_LINES (default 400)
#  10.  Files touched <= LEAF_PATCH_MAX_FILES (default 20)
#  11.  No file loses > LEAF_PATCH_MAX_DELETE_RATIO of its lines (default 0.5)
#
# Exit codes: 0=pass, 1=gate failed, 3=prereq missing

set -uo pipefail

_PV_ROOT="${_PV_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_PV_ROOT/core/brand/brand.sh"

LEAF_PATCH_MAX_LINES="${LEAF_PATCH_MAX_LINES:-400}"
LEAF_PATCH_MAX_FILES="${LEAF_PATCH_MAX_FILES:-20}"
LEAF_PATCH_MAX_DELETE_RATIO="${LEAF_PATCH_MAX_DELETE_RATIO:-0.5}"

# Secret-file deny-list patterns (substring match against normalized path)
[[ -v _PV_SECRET_PATTERNS ]] || readonly _PV_SECRET_PATTERNS=".env .env. secrets/ credentials/ id_rsa id_ed25519 id_ecdsa .pem .key .p12 .pfx .password .token .secret"

# ---------------------------------------------------------------------------
# patch_validate PATCH_FILE [ROOT_DIR]
# ---------------------------------------------------------------------------
patch_validate() {
	local patch="${1:-}"
	local root="${2:-$_PV_ROOT}"
	local fail=0

	command -v git &>/dev/null || {
		brand_warn "patch_validate: git is required"
		return 3
	}

	[[ -f "$patch" ]] || {
		_pv_fail "file exists" "not found: $patch"
		return 1
	}

	# 1. Non-empty ------------------------------------------------------------
	if [[ ! -s "$patch" ]]; then
		_pv_fail "non-empty" "patch file is empty"
		return 1
	fi
	_pv_ok "non-empty" "$(wc -c <"$patch") bytes"

	# 2. Looks like unified diff ----------------------------------------------
	if ! grep -q '^---' "$patch" || ! grep -q '^+++' "$patch"; then
		_pv_fail "unified diff format" "missing --- / +++ headers"
		(( fail++ ))
	else
		_pv_ok "unified diff format"
	fi

	[[ $fail -eq 0 ]] || { brand_warn "patch_validate: not a diff -- aborting further checks"; return 1; }

	# 3. git apply --check ----------------------------------------------------
	if ! git -C "$root" apply --check "$patch" 2>/dev/null; then
		_pv_fail "git apply --check" "patch would not apply cleanly"
		(( fail++ ))
	else
		_pv_ok "git apply --check"
	fi

	# 4. Path confinement (normalize, assert under root) ----------------------
	local root_real; root_real="$(cd "$root" && pwd)"
	local path_violations=0
	while IFS= read -r raw; do
		[[ -z "$raw" ]] && continue
		local norm; norm="$(python3 -c "
import os,sys
p=sys.argv[1]; r=sys.argv[2]
if not os.path.isabs(p): p=os.path.join(r,p)
print(os.path.realpath(p))" "$raw" "$root_real" 2>/dev/null || echo "$root_real/$raw")"
		if [[ "$norm" != "$root_real"* ]]; then
			_pv_fail "path confinement" "escapes root: '$raw'"
			(( fail++ )); (( path_violations++ ))
		fi
	done < <(grep '^+++ ' "$patch" | sed 's|^+++ [ab]/||;s|^+++ ||' | grep -v '/dev/null')

	[[ $path_violations -eq 0 ]] && _pv_ok "path confinement"

	# 5. No .git/ touches -----------------------------------------------------
	if grep -q '^+++ .*\.git/' "$patch" 2>/dev/null; then
		_pv_fail "no .git/ writes" "patch touches .git/"
		(( fail++ ))
	else
		_pv_ok "no .git/ writes"
	fi

	# 6. No secret/credential files -------------------------------------------
	local secret_violations=0
	while IFS= read -r touched; do
		for pat in $_PV_SECRET_PATTERNS; do
			if [[ "$touched" == *"$pat"* ]]; then
				_pv_fail "secret file deny-list" "touches: '$touched' (matched '$pat')"
				(( fail++ )); (( secret_violations++ ))
				break
			fi
		done
	done < <(grep '^+++ ' "$patch" | sed 's|^+++ [ab]/||;s|^+++ ||' | grep -v '/dev/null')

	[[ $secret_violations -eq 0 ]] && _pv_ok "secret file deny-list"

	# 7. No binary blobs ------------------------------------------------------
	if grep -q '^GIT binary patch' "$patch" 2>/dev/null; then
		_pv_fail "no binary blobs" "patch contains binary data"
		(( fail++ ))
	else
		_pv_ok "no binary blobs"
	fi

	# 8. No +x mode change or symlink addition --------------------------------
	if grep -qE '^(new file mode 100755|new file mode 120000|old mode [0-9]+ new mode 100755)' "$patch" 2>/dev/null; then
		_pv_fail "no +x / symlink" "patch adds executable mode or symlink"
		(( fail++ ))
	else
		_pv_ok "no +x / symlink"
	fi

	# 9. Changed lines <= LEAF_PATCH_MAX_LINES --------------------------------
	local added removed changed
	added="$(grep -c '^+[^+]' "$patch" 2>/dev/null || echo 0)"
	removed="$(grep -c '^-[^-]' "$patch" 2>/dev/null || echo 0)"
	changed=$(( added + removed ))
	if (( changed > LEAF_PATCH_MAX_LINES )); then
		_pv_fail "max changed lines" "${changed} lines > limit ${LEAF_PATCH_MAX_LINES}"
		(( fail++ ))
	else
		_pv_ok "max changed lines" "${changed} lines (limit: ${LEAF_PATCH_MAX_LINES})"
	fi

	# 10. Files touched <= LEAF_PATCH_MAX_FILES --------------------------------
	local file_count
	file_count="$(grep -c '^+++ ' "$patch" 2>/dev/null || echo 0)"
	if (( file_count > LEAF_PATCH_MAX_FILES )); then
		_pv_fail "max files touched" "${file_count} files > limit ${LEAF_PATCH_MAX_FILES}"
		(( fail++ ))
	else
		_pv_ok "max files touched" "${file_count} files (limit: ${LEAF_PATCH_MAX_FILES})"
	fi

	# 11. Delete ratio per file -----------------------------------------------
	# For each file in the patch, compare removed lines to original file line count
	local ratio_violations=0
	while IFS= read -r ppp_line; do
		local rel_path; rel_path="$(printf '%s' "$ppp_line" | sed 's|^+++ [ab]/||;s|^+++ ||')"
		[[ "$rel_path" == "/dev/null" ]] && continue
		local full_path="$root/$rel_path"
		[[ -f "$full_path" ]] || continue
		local orig_lines; orig_lines="$(wc -l <"$full_path")"
		(( orig_lines == 0 )) && continue
		# Count deletions for this file's hunk
		local file_del
		# Use awk to count '-' lines only within the hunk for this file
		file_del="$(awk -v target="$rel_path" '
			/^\+\+\+ / { in_file = ($0 ~ target) }
			in_file && /^-[^-]/ { count++ }
			END { print count+0 }
		' "$patch")"
		# Compare ratio using python (avoid floating point in bash)
		local over_ratio
		over_ratio="$(python3 -c "
del_r=${file_del}; orig=${orig_lines}; limit=${LEAF_PATCH_MAX_DELETE_RATIO}
print('1' if orig > 0 and del_r/orig > limit else '0')" 2>/dev/null || echo "0")"
		if [[ "$over_ratio" == "1" ]]; then
			_pv_fail "max delete ratio" "${rel_path}: ${file_del}/${orig_lines} lines deleted (limit: ${LEAF_PATCH_MAX_DELETE_RATIO})"
			(( fail++ )); (( ratio_violations++ ))
		fi
	done < <(grep '^+++ ' "$patch")

	[[ $ratio_violations -eq 0 ]] && _pv_ok "max delete ratio (per file)"

	# -- Result ---------------------------------------------------------------
	if [[ $fail -eq 0 ]]; then
		brand_ok "patch validated: $patch"
		return 0
	else
		brand_warn "patch validation failed: $fail check(s) did not pass"
		return 1
	fi
}

# ---------------------------------------------------------------------------
# patch_preview PATCH_FILE
# Render the diff; no mutation.
# ---------------------------------------------------------------------------
patch_preview() {
	local patch="${1:-}"
	[[ -f "$patch" ]] || { brand_warn "patch_preview: not found: $patch"; return 1; }
	brand_header "patch preview: ${patch##*/}"
	if command -v git &>/dev/null; then
		git diff --no-index --stat /dev/null "$patch" 2>/dev/null || true
	fi
	cat "$patch"
}

_pv_ok() {
	local rule="$1" detail="${2:-}"
	printf '  [ok]   %s' "$rule"
	[[ -n "$detail" ]] && printf '  (%s)' "$detail"
	printf '\n'
}

_pv_fail() {
	local rule="$1" detail="${2:-}"
	printf '  [fail] %s' "$rule"
	[[ -n "$detail" ]] && printf '  -- %s' "$detail"
	printf '\n'
}
