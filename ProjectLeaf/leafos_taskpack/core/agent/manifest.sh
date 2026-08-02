#!/usr/bin/env bash
# core/agent/manifest.sh  --  Run directory management (WO-007-C §5)
#
# Layout:
#   runs/
#     YYYY-MM-DD_HHMMSS/
#       manifest.json       index of this run
#       provider.env        contract env, secrets redacted
#       prompt.txt          task prompt, secrets redacted
#       response.raw.txt    exactly what the model emitted (written by adapter)
#       response.clean.txt  fences stripped, normalized
#       agent.graph.json
#       patch.diff
#       validation.log
#       report.md
#     latest -> YYYY-MM-DD_HHMMSS   (symlink, flipped atomically after run completes)
#
# Rules:
#   - Run id = YYYY-MM-DD_HHMMSS; collision -> append _2, _3, ...
#   - Each artifact written atomically (tmp+rename)
#   - provider.env and prompt.txt pass through redactor before writing
#   - latest symlink flipped only after run directory is complete

set -uo pipefail

_MF_ROOT="${_MF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_MF_ROOT/core/brand/brand.sh"

LEAF_RUNS_DIR="${LEAF_RUNS_DIR:-$_MF_ROOT/runs}"

# Redact patterns: these env var name fragments trigger redaction
[[ -v _MF_SECRET_VARS ]] || readonly _MF_SECRET_VARS="KEY SECRET TOKEN PASSWORD PASS CRED API_KEY"

# ---------------------------------------------------------------------------
# manifest_run_dir_new  →  stdout: path to new run directory
# Creates the directory; does NOT write manifest.json yet.
# ---------------------------------------------------------------------------
manifest_run_dir_new() {
	local base_id; base_id="$(date -u '+%Y-%m-%d_%H%M%S')"
	local run_dir="$LEAF_RUNS_DIR/$base_id"

	# Collision handling: append _2, _3, ... (rare but correct)
	local suffix=1
	while [[ -e "$run_dir" ]]; do
		(( suffix++ ))
		run_dir="$LEAF_RUNS_DIR/${base_id}_${suffix}"
	done

	mkdir -p "$run_dir"
	printf '%s\n' "$run_dir"
}

# ---------------------------------------------------------------------------
# manifest_write RUN_DIR STATUS [extra key=value ...]
# Write manifest.json atomically.
# STATUS: running|completed|failed
# ---------------------------------------------------------------------------
manifest_write() {
	local run_dir="$1" status="$2"
	shift 2
	local run_id; run_id="$(basename "$run_dir")"
	local now; now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

	# Build extra fields from key=value args
	local extra_json="{}"
	while [[ $# -gt 0 ]]; do
		local kv="$1"; shift
		local k="${kv%%=*}" v="${kv#*=}"
		extra_json="$(printf '%s' "$extra_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
d['${k}']='${v}'
print(json.dumps(d))" 2>/dev/null || echo "$extra_json")"
	done

	# Collect artifact inventory
	local artifacts="[]" hashes="{}"
	local f
	for f in "$run_dir"/*; do
		[[ -f "$f" ]] || continue
		[[ "$(basename "$f")" == "manifest.json" ]] && continue
		local fname; fname="$(basename "$f")"
		artifacts="$(printf '%s' "$artifacts" | python3 -c "
import json,sys
arr=json.load(sys.stdin); arr.append('${fname}'); print(json.dumps(arr))" 2>/dev/null || echo "$artifacts")"
		local digest
		digest="$(sha256sum "$f" 2>/dev/null | awk '{print $1}')"
		if [[ -n "$digest" ]]; then
			hashes="$(printf '%s' "$hashes" | python3 -c "
import json,sys
value=json.load(sys.stdin); value['${fname}']='${digest}'; print(json.dumps(value, sort_keys=True))" 2>/dev/null || echo "$hashes")"
		fi
	done

	local tmp; tmp="$run_dir/manifest.json.tmp.$$"
	python3 -c "
import json, sys
base = json.loads(sys.argv[1])
extra = json.loads(sys.argv[2])
arts = json.loads(sys.argv[3])
base.update(extra)
base['artifacts'] = arts
base['artifact_hashes'] = json.loads(sys.argv[4])
print(json.dumps(base, indent=2))
" \
	"{\"run_id\":\"$run_id\",\"status\":\"$status\",\"timestamp\":\"$now\",\"provider\":\"${LEAF_PROVIDER_NAME:-}\",\"model\":\"${LEAF_PROVIDER_MODEL:-}\",\"ms\":${LEAF_PROVIDER_MS:-0}}" \
	"$extra_json" \
	"$artifacts" \
	"$hashes" >"$tmp" 2>/dev/null && mv "$tmp" "$run_dir/manifest.json" \
		|| { rm -f "$tmp"; brand_warn "manifest_write: failed to write manifest"; return 1; }
}

# ---------------------------------------------------------------------------
# manifest_write_env RUN_DIR
# Write provider.env (contract env vars), secrets redacted.
# ---------------------------------------------------------------------------
manifest_write_env() {
	local run_dir="$1"
	local tmp; tmp="$run_dir/provider.env.tmp.$$"
	{
		printf '# provider.env -- contract snapshot (secrets redacted)\n'
		for var in LEAF_PROVIDER_OK LEAF_PROVIDER_NAME LEAF_PROVIDER_MODEL \
				   LEAF_PROVIDER_TEXT_FILE LEAF_PROVIDER_BYTES LEAF_PROVIDER_MS \
				   LEAF_PROVIDER_ERROR LEAF_PROVIDER_CONTRACT \
				   LEAF_PROVIDER_MODE LEAF_OLLAMA_HOST LEAF_OLLAMA_MODEL; do
			[[ -v "$var" ]] || continue
			printf '%s=%s\n' "$var" "${!var}"
		done
	} >"$tmp"
	mv "$tmp" "$run_dir/provider.env"
}

# ---------------------------------------------------------------------------
# manifest_write_prompt RUN_DIR PROMPT_TEXT
# Write prompt.txt, secrets redacted.
# ---------------------------------------------------------------------------
manifest_write_prompt() {
	local run_dir="$1" prompt="$2"
	local tmp; tmp="$run_dir/prompt.txt.tmp.$$"
	printf '%s' "$prompt" | _manifest_redact >"$tmp"
	mv "$tmp" "$run_dir/prompt.txt"
}

# ---------------------------------------------------------------------------
# manifest_write_clean RUN_DIR
# Create response.clean.txt by stripping fences from response.raw.txt.
# ---------------------------------------------------------------------------
manifest_write_clean() {
	local run_dir="$1"
	local raw="$run_dir/response.raw.txt"
	[[ -f "$raw" ]] || return 0
	local tmp; tmp="$run_dir/response.clean.txt.tmp.$$"
	python3 -c "
import re, sys
text = sys.stdin.read()
text = re.sub(r'^\s*\x60\x60\x60(?:bash|diff|patch|sh)?\n?', '', text, flags=re.MULTILINE)
text = re.sub(r'\x60\x60\x60\s*\n', '\n', text)
text = text.strip()
print(text)
" <"$raw" >"$tmp" 2>/dev/null && mv "$tmp" "$run_dir/response.clean.txt" \
		|| { rm -f "$tmp"; brand_warn "manifest_write_clean: python3 required"; }
}

# ---------------------------------------------------------------------------
# manifest_symlink_latest RUN_DIR
# Atomically flip runs/latest to point at the completed run directory.
# ---------------------------------------------------------------------------
manifest_symlink_latest() {
	local run_dir="$1"
	local latest_link="$LEAF_RUNS_DIR/latest"
	local run_name; run_name="$(basename "$run_dir")"

	# Atomic: create a temp symlink then rename
	local tmp_link; tmp_link="$LEAF_RUNS_DIR/.latest_tmp_$$"
	ln -sfn "$run_name" "$tmp_link" && mv -f "$tmp_link" "$latest_link" \
		|| { rm -f "$tmp_link"; brand_warn "manifest_symlink_latest: failed to flip symlink"; return 1; }
}

# ---------------------------------------------------------------------------
# _manifest_redact  (stdin → stdout)
# Replace API key values and similar secrets with [REDACTED].
# ---------------------------------------------------------------------------
_manifest_redact() {
	python3 -c "
import sys, re
text = sys.stdin.read()
# Redact env-var assignments that look like secrets
text = re.sub(r'(?i)(api[_\-]?key|secret|token|password|credential)\s*=\s*\S+',
			  r'\1=[REDACTED]', text)
# Redact Bearer tokens
text = re.sub(r'Bearer\s+[A-Za-z0-9\-_\.]+', 'Bearer [REDACTED]', text)
sys.stdout.write(text)
" 2>/dev/null || cat  # fallback: pass through unredacted if python3 unavailable
}
