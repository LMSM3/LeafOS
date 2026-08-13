#!/usr/bin/env bash
# Shared branding helpers for shell frontends.

set -u

# shellcheck source=../system/paths.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/system/paths.sh"

BRAND_CONFIG="${BRAND_CONFIG:-$LEAF_CONFIG_DIR/brand.conf}"
[[ -f "$BRAND_CONFIG" ]] && source "$BRAND_CONFIG"

PROJECT_NAME="${PROJECT_NAME:-LeafOS}"
PROJECT_CLI="${PROJECT_CLI:-leafctl}"
FLOWER_EMOJI_RATE="${FLOWER_EMOJI_RATE:-2}"
FLOWER_EMOJI="${FLOWER_EMOJI:-✿}"
DEFAULT_ICON="${DEFAULT_ICON:-›}"
BANNER_ENABLED="${BANNER_ENABLED:-1}"
QUIET="${QUIET:-0}"
NO_EMOJI="${NO_EMOJI:-0}"
NO_COLOR="${NO_COLOR:-0}"

# Keep one shell palette authority so installers, glyphs, and legacy brand
# helpers cannot silently diverge.
# shellcheck source=palette.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/palette.sh"

__brand_msg_count=0

brand_icon() {
    __brand_msg_count=$((__brand_msg_count + 1))
    if [[ "$NO_EMOJI" == "1" || "$FLOWER_EMOJI_RATE" -le 0 ]]; then
        printf '%s' "$DEFAULT_ICON"
        return
    fi
    if (( __brand_msg_count % FLOWER_EMOJI_RATE == 0 )); then
        printf '%s' "$FLOWER_EMOJI"
    else
        printf '%s' "$DEFAULT_ICON"
    fi
}

brand_say() {
    [[ "$QUIET" == "1" ]] && return 0
    printf '%s%s%s [%s%s%s] %s\n' \
        "$C_CYAN" "$(brand_icon)" "$C_RESET" \
        "$C_BOLD" "$PROJECT_NAME" "$C_RESET" \
        "$*"
}

brand_plain() {
    [[ "$QUIET" == "1" ]] && return 0
    printf '%s\n' "$*"
}

brand_warn() {
    printf '%s%s [%s] warning:%s %s\n' \
        "$C_YELLOW_B" "!" "$PROJECT_NAME" "$C_RESET" "$*" >&2
}

brand_die() {
    printf '%s%s [%s] error:%s %s\n' \
        "$C_RED_B" "✗" "$PROJECT_NAME" "$C_RESET" "$*" >&2
    exit 1
}

# brand_ok MSG -- green success line
brand_ok() {
    [[ "$QUIET" == "1" ]] && return 0
    printf '%s✓%s %s\n' "$C_GREEN_B" "$C_RESET" "$*"
}

# brand_header TITLE -- bold full-width section divider
brand_header() {
    [[ "$QUIET" == "1" ]] && return 0
    local title="$*"
    local width=60
    local line
    printf -v line '%*s' "$width" ''
    printf '\n%s%s%s\n' "$C_CYAN_B" "${line// /─}" "$C_RESET"
    printf ' %s%s%s%s%s\n' "$C_BOLD" "$C_CYAN" "  $title" "$C_RESET" ""
    printf '%s%s%s\n' "$C_CYAN_B" "${line// /─}" "$C_RESET"
}

# brand_step N LABEL -- colored numbered step line
brand_step() {
    [[ "$QUIET" == "1" ]] && return 0
    local n="$1"; shift
    printf ' %s[%s%s%s]%s %s\n' \
        "$C_DIM" "$C_CYAN_B" "$n" "$C_DIM" "$C_RESET" "$*"
}

# brand_kv KEY VALUE -- aligned key/value pair
brand_kv() {
    [[ "$QUIET" == "1" ]] && return 0
    printf '  %s%-18s%s %s%s%s\n' \
        "$C_DIM" "$1" "$C_RESET" "$C_CYAN" "$2" "$C_RESET"
}

brand_banner() {
    [[ "$BANNER_ENABLED" == "1" && "$QUIET" != "1" ]] || return 0
    local width=60
    local line
    printf -v line '%*s' "$width" ''
    printf '\n%s%s%s\n' "$C_GREEN_B" "${line// /━}" "$C_RESET"
    printf '  %s%s%s   %s%s%s\n' \
        "$C_BOLD" "$PROJECT_NAME" "$C_RESET" \
        "$C_DIM" "local terminal control layer" "$C_RESET"
    printf '%s%s%s\n\n' "$C_GREEN_B" "${line// /━}" "$C_RESET"
}

