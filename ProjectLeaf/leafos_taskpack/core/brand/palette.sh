#!/usr/bin/env bash
# Canonical LeafOS/FlowerOS terminal palette.
# Safe to source before or after `set -u`; does not change caller shell options.

leaf_color_enabled() {
    [[ "${NO_COLOR:-0}" != "1" ]] || return 1
    case "${LEAF_COLOR:-${FORCE_COLOR:-0}}" in
        1|yes|true|YES|TRUE) return 0 ;;
    esac
    [[ -t 1 ]]
}

# Terminal motion is independent from color and Unicode.  Automatic mode only
# animates an interactive terminal; redirected output receives stable lines.
# Explicit accessibility flags always win over a forced animation.
leaf_motion_enabled() {
    case "${NO_ANIMATION:-0}:${LEAF_NO_ANIMATION:-0}:${REDUCE_MOTION:-0}" in
        1:*|*:1:*|*:*:1) return 1 ;;
    esac
    case "${LEAF_MOTION:-auto}" in
        0|off|never|reduce|reduced|OFF|NEVER|REDUCE|REDUCED) return 1 ;;
        1|on|always|force|ON|ALWAYS|FORCE) return 0 ;;
        auto|AUTO|'') ;;
        *) return 1 ;;
    esac
    [[ "${TERM:-}" != "dumb" ]] || return 1
    [[ -t 1 ]]
}

leaf_unicode_enabled() {
    case "${NO_EMOJI:-0}:${LEAF_NO_EMOJI:-0}:${LEAF_GLYPHS:-auto}" in
        1:*|*:1:*|*:*:ascii|*:*:ASCII) return 1 ;;
        *:*:unicode|*:*:UNICODE) return 0 ;;
    esac
    return 0
}

leaf_motion_delay() {
    local fallback="${1:-0.08}"
    local selected="${LEAF_ANIMATION_DELAY:-$fallback}"
    if [[ "$selected" =~ ^([0-9]+)(\.[0-9]+)?$ ]]; then
        printf '%s' "$selected"
    else
        printf '%s' "$fallback"
    fi
}

_leaf_transition_frames() {
    local style="${1:-leaf}"
    if leaf_unicode_enabled; then
        case "$style" in
            orbit)    printf '◐ ◓ ◑ ◒\n' ;;
            bloom)    printf '· ✿ ❀ ✽ ❁\n' ;;
            comet)    printf '⠁ ⠂ ⠄ ⠂\n' ;;
            braille)  printf '⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏\n' ;;
            model)    printf 'GGUF Q4 LOCAL READY\n' ;;
            download) printf '🌱 🌿 GGUF ↓ ✓\n' ;;
            *)        printf '🍃 🌿 ☘ 🌱\n' ;;
        esac
    else
        case "$style" in
            bloom)    printf '. o O o\n' ;;
            comet)    printf '. .. ... ..\n' ;;
            model)    printf 'GGUF Q4 LOCAL READY\n' ;;
            download) printf 'PLAN FETCH HASH READY\n' ;;
            *)        printf '| / - \\\n' ;;
        esac
    fi
}

# leaf_transition LABEL [STYLE [CYCLES [DELAY]]]
# A bounded entry transition.  It ends at READY and never claims the command
# itself completed; callers report real success/failure after execution.
leaf_transition() {
    local label="${1:-preparing}"
    local style="${2:-leaf}"
    local cycles="${3:-10}"
    local delay="${4:-$(leaf_motion_delay 0.07)}"
    if ! leaf_motion_enabled; then
        printf '  [READY] %s\n' "$label"
        return 0
    fi
    [[ "$cycles" =~ ^[1-9][0-9]*$ ]] || cycles=10
    local frames=()
    IFS=' ' read -r -a frames <<< "$(_leaf_transition_frames "$style")"
    local count="${#frames[@]}"
    local i
    for ((i=0; i<cycles; i++)); do
        printf '\r\033[2K  %s%s%s %s' \
            "$C_SKY" "${frames[$((i % count))]}" "$C_RESET" "$label"
        sleep "$delay"
    done
    printf '\r\033[2K  %s[READY]%s %s\n' "$C_LEAF" "$C_RESET" "$label"
}

leaf_palette_init() {
    if ! leaf_color_enabled; then
        C_RESET=''; C_BOLD=''; C_DIM=''
        C_MINT=''; C_LEAF=''; C_FERN=''; C_FOREST=''
        C_BLOOM=''; C_LAVENDER=''; C_SKY=''; C_BUTTER=''; C_PEACH=''; C_ERROR=''
        C_GREEN=''; C_CYAN=''; C_YELLOW=''; C_RED=''; C_MAGENTA=''; C_BLUE=''
        C_GREEN_B=''; C_CYAN_B=''; C_YELLOW_B=''; C_RED_B=''
        return
    fi

    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_MINT=$'\033[38;2;183;240;199m'
    C_LEAF=$'\033[38;2;119;221;119m'
    C_FERN=$'\033[38;2;80;180;80m'
    C_FOREST=$'\033[38;2;34;139;34m'
    C_BLOOM=$'\033[38;2;255;183;197m'
    C_LAVENDER=$'\033[38;2;204;178;255m'
    C_SKY=$'\033[38;2;178;223;255m'
    C_BUTTER=$'\033[38;2;255;250;181m'
    C_PEACH=$'\033[38;2;255;210;183m'
    C_ERROR=$'\033[38;2;255;154;162m'

    C_GREEN="$C_LEAF"; C_CYAN="$C_SKY"; C_YELLOW="$C_BUTTER"
    C_RED="$C_ERROR"; C_MAGENTA="$C_BLOOM"; C_BLUE="$C_SKY"
    C_GREEN_B="$C_BOLD$C_LEAF"; C_CYAN_B="$C_BOLD$C_SKY"
    C_YELLOW_B="$C_BOLD$C_BUTTER"; C_RED_B="$C_BOLD$C_ERROR"
}

leaf_palette_init
