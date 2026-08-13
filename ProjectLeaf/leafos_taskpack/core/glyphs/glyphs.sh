#!/usr/bin/env bash
# LeafOS symbolic glyph runtime.
#
# Soft surface, hard backend: the registry (config/glyphs.conf) stores only
# Unicode codepoints in pure ASCII; this layer renders them to UTF-8 on demand
# and resolves severity/color at call time. Decorative output must never hide
# failure -- leaf_alert colors by state, not by vibe.

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/brand/brand.sh"

GLYPH_CONFIG="${GLYPH_CONFIG:-$LEAF_CONFIG_DIR/glyphs.conf}"

declare -A _LEAF_GLYPH_CP
declare -A _LEAF_GLYPH_CAT
declare -A _LEAF_GLYPH_SEV
declare -A _LEAF_GLYPH_ASCII
declare -A _LEAF_GLYPH_MEAN
_LEAF_GLYPH_LOADED=0
_LEAF_SESSION_VERIFIED=0   # set only by leaf_verify_run on pass

_leaf_glyph_ascii_mode() {
	[[ "${NO_EMOJI:-0}" == "1" || "${LEAF_NO_EMOJI:-0}" == "1" ]]
}

# Severity -> ANSI color. Empty when color is disabled or stdout is not a tty.
_leaf_color() {
	local sev="$1"
	local off=0
	if [[ "${NO_COLOR:-0}" == "1" ]]; then
		off=1
	elif [[ "${LEAF_COLOR:-${FORCE_COLOR:-0}}" != "1" && ! -t 1 ]]; then
		off=1
	fi
	if (( off )); then
		printf ''
		return
	fi
	case "$sev" in
		error) printf '%s' "$C_ERROR" ;;
		warn)  printf '%s' "$C_BUTTER" ;;
		ok)    printf '%s' "$C_LEAF" ;;
		info)  printf '%s' "$C_SKY" ;;
		*)     printf '' ;;
	esac
}
_leaf_reset() {
	local off=0
	if [[ "${NO_COLOR:-0}" == "1" ]]; then
		off=1
	elif [[ "${LEAF_COLOR:-${FORCE_COLOR:-0}}" != "1" && ! -t 1 ]]; then
		off=1
	fi
	(( off )) && return
	printf '%s' "$C_RESET"
}

# Convert one or more hex codepoints to UTF-8 bytes. Pure-bash encoder using
# \xHH byte escapes so we never rely on printf \u/\U support.
_leaf_cp_to_utf8() {
	local cp_hex cp out=""
	for cp_hex in "$@"; do
		[[ "$cp_hex" =~ ^[0-9A-F]{4,6}$ ]] || return 1
		cp=$((16#$cp_hex))
		(( cp > 0 && cp <= 0x10FFFF )) || return 1
		(( cp < 0xD800 || cp > 0xDFFF )) || return 1
		if (( cp <= 0x7F )); then
			out+=$(printf '\\x%02X' "$cp")
		elif (( cp <= 0x7FF )); then
			out+=$(printf '\\x%02X\\x%02X' \
				$(( 0xC0 | (cp >> 6) )) \
				$(( 0x80 | (cp & 0x3F) )))
		elif (( cp <= 0xFFFF )); then
			out+=$(printf '\\x%02X\\x%02X\\x%02X' \
				$(( 0xE0 | (cp >> 12) )) \
				$(( 0x80 | ((cp >> 6) & 0x3F) )) \
				$(( 0x80 | (cp & 0x3F) )))
		else
			out+=$(printf '\\x%02X\\x%02X\\x%02X\\x%02X' \
				$(( 0xF0 | (cp >> 18) )) \
				$(( 0x80 | ((cp >> 12) & 0x3F) )) \
				$(( 0x80 | ((cp >> 6) & 0x3F) )) \
				$(( 0x80 | (cp & 0x3F) )))
		fi
	done
	printf '%b' "$out"
}

leaf_glyph_reset() {
	_LEAF_GLYPH_CP=()
	_LEAF_GLYPH_CAT=()
	_LEAF_GLYPH_SEV=()
	_LEAF_GLYPH_ASCII=()
	_LEAF_GLYPH_MEAN=()
	_LEAF_GLYPH_LOADED=0
}

_leaf_glyph_registry_error() {
	local line_no="$1"
	shift
	printf 'glyph registry error at line %s: %s\n' "$line_no" "$*" >&2
	return 1
}

leaf_glyph_load() {
	[[ "$_LEAF_GLYPH_LOADED" == "1" ]] && return 0
	[[ -f "$GLYPH_CONFIG" ]] || {
		printf 'glyph registry not found: %s\n' "$GLYPH_CONFIG" >&2
		return 1
	}

	leaf_glyph_reset
	local line alias cps cat sev ascii mean extra cp cp_value line_no=0
	while IFS= read -r line || [[ -n "$line" ]]; do
		((line_no += 1))
		[[ "$line" =~ ^[[:space:]]*$ || "$line" =~ ^[[:space:]]*# ]] && continue
		IFS='|' read -r alias cps cat sev ascii mean extra <<< "$line"
		[[ -z "$extra" ]] || {
			_leaf_glyph_registry_error "$line_no" "expected exactly six fields"
			return 1
		}
		[[ "$alias" =~ ^[a-z][a-z0-9]*(\.[a-z0-9]+)*$ ]] || {
			_leaf_glyph_registry_error "$line_no" "invalid alias '$alias'"
			return 1
		}
		[[ -z "${_LEAF_GLYPH_CP[$alias]+present}" ]] || {
			_leaf_glyph_registry_error "$line_no" "duplicate alias '$alias'"
			return 1
		}
		case "$cat" in
			identity|growth|flower|flow|model|verify|status|loading|io|data|cosmetic) ;;
			*)
				_leaf_glyph_registry_error "$line_no" "invalid category '$cat'"
				return 1
				;;
		esac
		case "$sev" in
			none|info|ok|warn|error) ;;
			*)
				_leaf_glyph_registry_error "$line_no" "invalid severity '$sev'"
				return 1
				;;
		esac
		[[ -n "$cps" && -n "$ascii" && -n "$mean" ]] || {
			_leaf_glyph_registry_error "$line_no" "codepoints, ascii, and meaning are required"
			return 1
		}
		LC_ALL=C grep -Eq '^[ -~]+$' <<< "$ascii" || {
			_leaf_glyph_registry_error "$line_no" "ASCII fallback must contain printable ASCII only"
			return 1
		}
		for cp in $cps; do
			[[ "$cp" =~ ^[0-9A-F]{4,6}$ ]] || {
				_leaf_glyph_registry_error "$line_no" "invalid codepoint '$cp'"
				return 1
			}
			cp_value=$((16#$cp))
			(( cp_value > 0 && cp_value <= 0x10FFFF )) || {
				_leaf_glyph_registry_error "$line_no" "codepoint out of range '$cp'"
				return 1
			}
			(( cp_value < 0xD800 || cp_value > 0xDFFF )) || {
				_leaf_glyph_registry_error "$line_no" "surrogate codepoint '$cp'"
				return 1
			}
		done
		_LEAF_GLYPH_CP["$alias"]="$cps"
		_LEAF_GLYPH_CAT["$alias"]="$cat"
		_LEAF_GLYPH_SEV["$alias"]="$sev"
		_LEAF_GLYPH_ASCII["$alias"]="$ascii"
		_LEAF_GLYPH_MEAN["$alias"]="$mean"
	done < "$GLYPH_CONFIG"
	[[ "${#_LEAF_GLYPH_CP[@]}" -gt 0 ]] || {
		_leaf_glyph_registry_error 0 "registry is empty"
		return 1
	}
	_LEAF_GLYPH_LOADED=1
}

leaf_glyph_exists() {
	leaf_glyph_load || return 1
	[[ -n "${_LEAF_GLYPH_CP[${1:-}]+present}" ]]
}

# leaf_glyph ALIAS -- render glyph for an alias (ascii fallback honored).
leaf_glyph() {
	leaf_glyph_load
	local alias="${1:-}"
	local cps="${_LEAF_GLYPH_CP[$alias]:-}"
	if [[ -z "$cps" ]]; then
		printf '%s' "${DEFAULT_ICON}"
		return 1
	fi
	if _leaf_glyph_ascii_mode; then
		printf '%s' "${_LEAF_GLYPH_ASCII[$alias]:-$DEFAULT_ICON}"
		return 0
	fi
	# shellcheck disable=SC2086
	_leaf_cp_to_utf8 $cps
}

# leaf_glyph_ascii ALIAS -- degraded ASCII fallback marker.
leaf_glyph_ascii() {
	leaf_glyph_load
	printf '%s' "${_LEAF_GLYPH_ASCII[${1:-}]:-$DEFAULT_ICON}"
}

# leaf_glyph_meaning ALIAS -- human-readable description.
leaf_glyph_meaning() {
	leaf_glyph_load
	printf '%s' "${_LEAF_GLYPH_MEAN[${1:-}]:-unknown glyph}"
}

_leaf_json_escape() {
	local value="${1:-}"
	value=${value//\\/\\\\}
	value=${value//\"/\\\"}
	value=${value//$'\b'/\\b}
	value=${value//$'\f'/\\f}
	value=${value//$'\n'/\\n}
	value=${value//$'\r'/\\r}
	value=${value//$'\t'/\\t}
	printf '%s' "$value"
}

# leaf_glyph_object ALIAS [auto|unicode|ascii] -- versioned JSON glyph object.
leaf_glyph_object() {
	leaf_glyph_load || return 1
	local alias="${1:-}"
	local requested_mode="${2:-auto}"
	leaf_glyph_exists "$alias" || return 1

	local render_mode
	case "$requested_mode" in
		auto)
			if _leaf_glyph_ascii_mode; then render_mode="ascii"; else render_mode="unicode"; fi
			;;
		unicode|ascii) render_mode="$requested_mode" ;;
		*)
			printf 'invalid glyph render mode: %s\n' "$requested_mode" >&2
			return 1
			;;
	esac

	local rendered
	if [[ "$render_mode" == "ascii" ]]; then
		rendered="${_LEAF_GLYPH_ASCII[$alias]}"
	else
		# shellcheck disable=SC2086
		rendered="$(_leaf_cp_to_utf8 ${_LEAF_GLYPH_CP[$alias]})"
	fi

	local cp codepoints_json="" separator=""
	for cp in ${_LEAF_GLYPH_CP[$alias]}; do
		codepoints_json+="${separator}\"$cp\""
		separator=","
	done
	printf '{"leafos_object":"leafos.glyph","version":1,"alias":"%s","glyph":"%s","codepoints":[%s],"category":"%s","severity":"%s","ascii":"%s","meaning":"%s","render_mode":"%s"}\n' \
		"$(_leaf_json_escape "$alias")" \
		"$(_leaf_json_escape "$rendered")" \
		"$codepoints_json" \
		"$(_leaf_json_escape "${_LEAF_GLYPH_CAT[$alias]}")" \
		"$(_leaf_json_escape "${_LEAF_GLYPH_SEV[$alias]}")" \
		"$(_leaf_json_escape "${_LEAF_GLYPH_ASCII[$alias]}")" \
		"$(_leaf_json_escape "${_LEAF_GLYPH_MEAN[$alias]}")" \
		"$render_mode"
}

# leaf_glyph_registry_object [CATEGORY] [auto|unicode|ascii] -- JSON envelope.
leaf_glyph_registry_object() {
	leaf_glyph_load || return 1
	local category="${1:-}"
	local requested_mode="${2:-auto}"
	local render_mode
	case "$requested_mode" in
		auto)
			if _leaf_glyph_ascii_mode; then render_mode="ascii"; else render_mode="unicode"; fi
			;;
		unicode|ascii) render_mode="$requested_mode" ;;
		*)
			printf 'invalid glyph render mode: %s\n' "$requested_mode" >&2
			return 1
			;;
	esac

	local aliases=() alias count=0 separator=""
	mapfile -t aliases < <(printf '%s\n' "${!_LEAF_GLYPH_CP[@]}" | LC_ALL=C sort)
	for alias in "${aliases[@]}"; do
		[[ -n "$category" && "${_LEAF_GLYPH_CAT[$alias]}" != "$category" ]] && continue
		((count += 1))
	done

	printf '{"leafos_object":"leafos.glyph_registry","version":1,"category":"%s","count":%d,"render_mode":"%s","glyphs":[' \
		"$(_leaf_json_escape "$category")" "$count" "$render_mode"
	for alias in "${aliases[@]}"; do
		[[ -n "$category" && "${_LEAF_GLYPH_CAT[$alias]}" != "$category" ]] && continue
		printf '%s' "$separator"
		leaf_glyph_object "$alias" "$render_mode" | tr -d '\n'
		separator=","
	done
	printf ']}\n'
}

# leaf_glyph_list [category] -- list registry rows, optionally filtered.
leaf_glyph_list() {
	leaf_glyph_load
	local want="${1:-}"
	local alias
	for alias in "${!_LEAF_GLYPH_CP[@]}"; do
		[[ -n "$want" && "${_LEAF_GLYPH_CAT[$alias]}" != "$want" ]] && continue
		printf '%s\t%s\t%s\n' "$(leaf_glyph "$alias")" "$alias" "${_LEAF_GLYPH_MEAN[$alias]}"
	done | sort -t$'\t' -k2,2
}

# leaf_verify_run CMD [LABEL] -- run CMD as the verification check.
# Only emits leaf.verify and sets the session flag on exit 0.
# On failure: emits leaf.fail glyph + a leaf.alert error. Never lies.
leaf_verify_run() {
	leaf_glyph_load
	local cmd=("$@")
	local label="${cmd[*]}"
	local rc=0
	"${cmd[@]}" 2>&1 || rc=$?
	if [[ $rc -eq 0 ]]; then
		_LEAF_SESSION_VERIFIED=1
		printf '%s %s\n' "$(leaf_glyph leaf.verify)" "verified: $label"
		_leaf_machine_log verify ok "$label"
	else
		_LEAF_SESSION_VERIFIED=0
		printf '%s %s\n' "$(leaf_glyph leaf.fail)" "failed: $label" >&2
		_leaf_machine_log verify fail "$label (exit $rc)"
		leaf_alert error "check failed: $label (exit $rc)"
		return $rc
	fi
}

# leaf_checkpoint_create LABEL -- create a checkpoint.
# Refused unless the session verified flag is set by leaf_verify_run.
leaf_checkpoint_create() {
	leaf_glyph_load
	local label="${1:-checkpoint}"
	if [[ "$_LEAF_SESSION_VERIFIED" != "1" ]]; then
		leaf_alert error "checkpoint refused: leaf_verify_run must pass first"
		return 1
	fi
	printf '%s %s\n' "$(leaf_glyph leaf.checkpoint)" "checkpoint: $label"
	_leaf_machine_log checkpoint create "$label"
	_LEAF_SESSION_VERIFIED=0   # consumed; next checkpoint needs a new verify
}

# Internal: append a machine-readable event line to the session log.
_leaf_machine_log() {
	local kind="$1" result="$2" msg="$3"
	local logdir="${LEAF_LOG_DIR:-$LEAF_ROOT/logs}"
	mkdir -p "$logdir" 2>/dev/null || true
	printf '{"ts":"%s","kind":"%s","result":"%s","msg":"%s"}\n' \
		"$(_leaf_json_escape "$(date '+%Y-%m-%dT%H:%M:%S%z')")" \
		"$(_leaf_json_escape "$kind")" \
		"$(_leaf_json_escape "$result")" \
		"$(_leaf_json_escape "$msg")" \
		>> "$logdir/glyphs.jsonl"
}

# leaf_alert SEVERITY MESSAGE -- severity-aware alert. The glyph never carries
# severity; the state (color + label) does.
leaf_alert() {
	leaf_glyph_load
	local sev="${1:-warn}"; shift || true
	local msg="$*"
	local glyph color label
	glyph="$(leaf_glyph leaf.alert)"
	color="$(_leaf_color "$sev")"
	case "$sev" in
		error) label="error" ;;
		warn)  label="warning" ;;
		ok)    label="ok" ;;
		info)  label="info" ;;
		*)     label="$sev" ;;
	esac
	printf '%s%s %s:%s %s\n' "$color" "$glyph" "$label" "$(_leaf_reset)" "$msg" >&2
	_leaf_machine_log alert "$sev" "$msg"
}

# leaf_status ALIAS TEXT [ALIAS TEXT ...] -- compose a one-line status surface.
leaf_status() {
	leaf_glyph_load
	local out="" alias text first=1
	while [[ $# -gt 0 ]]; do
		alias="$1"; text="${2:-}"; shift 2 || shift $#
		if [[ $first -eq 1 ]]; then first=0; else out+="  "; fi
		out+="$(leaf_glyph "$alias") $text"
	done
	printf '%s\n' "$out"
	_leaf_machine_log status emit "$out"
}

# leaf_glyph_spinner
leaf_glyph_spinner() {
	local label="${1:-loading}"
	local cycles="${2:-12}"
	local delay="${3:-0.18}"
	local frames=(leaf.loading.a leaf.loading.b leaf.loading.c leaf.loading.d)
	local i
	for ((i=0; i<cycles; i++)); do
		printf '\r%s [%s] %s %s' "$(brand_icon)" "$PROJECT_NAME" "$label" \
			"$(leaf_glyph "${frames[$((i % 4))]}")"
		sleep "$delay"
	done
	printf '\r%s [%s] %s %s%*s\n' "$(brand_icon)" "$PROJECT_NAME" "$label" \
		"$(leaf_glyph leaf.verify)" 12 ""
}
