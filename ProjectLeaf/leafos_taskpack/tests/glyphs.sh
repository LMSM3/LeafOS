#!/usr/bin/env bash
# Tests for the LeafOS symbolic glyph layer.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/core/glyphs/glyphs.sh"

fail() { echo "glyph test FAILED: $*" >&2; exit 1; }
PYTHON_BIN="$(command -v python3 || command -v python || true)"
[[ -n "$PYTHON_BIN" ]] || fail "Python 3 is required for JSON assertions"

# Registry loads and is non-empty.
leaf_glyph_load
[[ "${#_LEAF_GLYPH_CP[@]}" -gt 0 ]] || fail "registry empty"

# Codepoint encoder produces correct UTF-8 bytes for a known BMP scalar (U+269D).
verify="$(leaf_glyph leaf.verify)"
bytes="$(printf '%s' "$verify" | od -An -tx1 | tr -s ' ')"
[[ "$bytes" == " e2 9a 9d" ]] || fail "leaf.verify bytes wrong: '$bytes'"

# Supplementary-plane scalar (U+13083) must encode to a 4-byte sequence.
flow="$(leaf_glyph leaf.flow)"
flow_bytes="$(printf '%s' "$flow" | od -An -tx1 | tr -s ' ')"
[[ "$flow_bytes" == " f0 93 82 83" ]] || fail "leaf.flow bytes wrong: '$flow_bytes'"

# Variation-selector sequence (U+26A0 U+FE0E) renders both codepoints.
alert_len="$(leaf_glyph leaf.alert | wc -c)"
[[ "$alert_len" -ge 6 ]] || fail "leaf.alert sequence too short: $alert_len"

# ASCII fallback path honors NO_EMOJI.
ascii="$(NO_EMOJI=1 leaf_glyph leaf.verify)"
[[ "$ascii" == "[ok]" ]] || fail "ascii fallback wrong: '$ascii'"

# PowerShell-compatible environment spelling also selects ASCII.
ascii="$(LEAF_NO_EMOJI=1 leaf_glyph leaf.verify)"
[[ "$ascii" == "[ok]" ]] || fail "LEAF_NO_EMOJI fallback wrong: '$ascii'"

# Unknown alias degrades to the default icon and returns non-zero.
if leaf_glyph leaf.nope >/dev/null 2>&1; then fail "unknown alias should fail"; fi

# Botanical expansion exposes both leaf and flower families with fallbacks.
[[ "$(leaf_glyph_ascii leaf.seedling)" == "(seed)" ]] || fail "leaf.seedling fallback missing"
[[ "$(leaf_glyph_ascii leaf.fallen)" == "(fall)" ]] || fail "leaf.fallen fallback missing"
[[ "$(leaf_glyph_ascii flower.active)" == "(*)" ]] || fail "flower.active fallback missing"
[[ "$(leaf_glyph_ascii flower.lotus)" == "(*)" ]] || fail "flower.lotus fallback missing"
leaf_glyph_list flower | grep -q $'flower.active\t' || fail "flower category missing"

# WO status, interconnection, stream, and object glyphs are first-class rows.
[[ "$(leaf_glyph_ascii leaf.status.todo)" == "[ ]" ]] || fail "todo fallback missing"
[[ "$(leaf_glyph_ascii leaf.status.active)" == "[>]" ]] || fail "active fallback missing"
[[ "$(leaf_glyph_ascii leaf.status.partial)" == "[/]" ]] || fail "partial fallback missing"
[[ "$(leaf_glyph_ascii leaf.status.done)" == "[+]" ]] || fail "done fallback missing"
[[ "$(leaf_glyph_ascii leaf.status.blocked)" == "[!]" ]] || fail "blocked fallback missing"
[[ "$(leaf_glyph_ascii leaf.status.deferred)" == "[--]" ]] || fail "deferred fallback missing"
[[ "$(leaf_glyph_ascii leaf.link)" == "<->" ]] || fail "link fallback missing"
[[ "$(leaf_glyph_ascii leaf.stream)" == "<=>" ]] || fail "stream fallback missing"
[[ "$(leaf_glyph_ascii leaf.object)" == "{}" ]] || fail "object fallback missing"

# Versioned glyph and registry objects remain valid JSON and carry full metadata.
glyph_json="$(leaf_glyph_object leaf.verify ascii)"
"$PYTHON_BIN" -c '
import json, sys
value = json.load(sys.stdin)
assert value["leafos_object"] == "leafos.glyph"
assert value["version"] == 1
assert value["alias"] == "leaf.verify"
assert value["glyph"] == "[ok]"
assert value["codepoints"] == ["269D"]
assert value["render_mode"] == "ascii"
' <<< "$glyph_json" || fail "glyph object JSON invalid"

registry_json="$(leaf_glyph_registry_object status ascii)"
"$PYTHON_BIN" -c '
import json, sys
value = json.load(sys.stdin)
assert value["leafos_object"] == "leafos.glyph_registry"
assert value["count"] == len(value["glyphs"])
assert value["count"] >= 6
assert all(item["category"] == "status" for item in value["glyphs"])
assert any(item["alias"] == "leaf.status.blocked" for item in value["glyphs"])
' <<< "$registry_json" || fail "glyph registry object JSON invalid"

# Alert severity labels resolve correctly.
leaf_alert error "x" 2>&1 | grep -q "error:" || fail "alert error label missing"
leaf_alert warn  "y" 2>&1 | grep -q "warning:" || fail "alert warn label missing"

# Every registry row has exactly six fields and a valid hex codepoint list.
while IFS='|' read -r alias cps cat sev ascii mean; do
	[[ -z "$alias" || "$alias" == \#* ]] && continue
	[[ -n "$cps" && -n "$cat" && -n "$sev" && -n "$ascii" && -n "$mean" ]] \
		|| fail "row '$alias' missing fields"
	[[ "$cps" =~ ^[0-9A-Fa-f\ ]+$ ]] || fail "row '$alias' bad codepoints: '$cps'"
done < "$GLYPH_CONFIG"

# Invalid Unicode scalar values fail closed during a fresh registry load.
invalid_registry="$(mktemp)"
printf 'leaf.invalid|D800|status|error|[x]|surrogate must fail\n' > "$invalid_registry"
if (
	GLYPH_CONFIG="$invalid_registry"
	leaf_glyph_reset
	leaf_glyph_load 2>/dev/null
); then
	rm -f "$invalid_registry"
	fail "surrogate registry row must be rejected"
fi
rm -f "$invalid_registry"
leaf_glyph_reset
leaf_glyph_load

# --- On-rails gating tests --------------------------------------------------

# leaf_checkpoint_create must refuse without a prior leaf_verify_run.
_LEAF_SESSION_VERIFIED=0
if leaf_checkpoint_create "pre-verify" 2>/dev/null; then
	fail "checkpoint must be refused before verify"
fi

# leaf_verify_run on a passing command sets the flag and emits leaf.verify.
_LEAF_SESSION_VERIFIED=0
verify_out="$(mktemp)"
leaf_verify_run true "true-check" >"$verify_out" 2>&1
[[ "$_LEAF_SESSION_VERIFIED" == "1" ]] || fail "session flag not set after passing verify"
grep -q "$(leaf_glyph leaf.verify)" "$verify_out" || fail "leaf.verify glyph not emitted on pass"
rm -f "$verify_out"

# leaf_verify_run on a failing command clears the flag and returns non-zero.
_LEAF_SESSION_VERIFIED=0
if leaf_verify_run false "false-check" 2>/dev/null; then
	fail "leaf_verify_run on false should fail"
fi
[[ "$_LEAF_SESSION_VERIFIED" == "0" ]] || fail "session flag must stay 0 after failing verify"

# leaf_checkpoint_create succeeds after a passing verify and clears the flag.
_LEAF_SESSION_VERIFIED=1
leaf_checkpoint_create "stable-0.2.0" >/dev/null
[[ "$_LEAF_SESSION_VERIFIED" == "0" ]] || fail "session flag must be consumed by checkpoint"

# machine log file is written.
logfile="${LEAF_LOG_DIR:-$ROOT_DIR/logs}/glyphs.jsonl"
[[ -f "$logfile" ]] || fail "machine log not written: $logfile"
grep -q '"kind":"verify"' "$logfile" || fail "verify entry missing from machine log"

# Quoted messages must remain parseable JSONL.
_leaf_machine_log alert info 'quoted "message"'
tail -n 1 "$logfile" | "$PYTHON_BIN" -c '
import json, sys
value = json.load(sys.stdin)
assert value["msg"] == "quoted \"message\""
' || fail "quoted machine log entry is not valid JSON"

echo "glyph tests passed"
