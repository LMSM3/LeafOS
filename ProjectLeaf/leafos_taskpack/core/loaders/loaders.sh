#!/usr/bin/env bash
# Universal loading animations for LeafOS.

set -u
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/brand/brand.sh"

LOADER_CONFIG="${LOADER_CONFIG:-$LEAF_CONFIG_DIR/loaders.conf}"
[[ -f "$LOADER_CONFIG" ]] && source "$LOADER_CONFIG"

DEFAULT_LOADER="${DEFAULT_LOADER:-dots3}"
DEFAULT_DELAY="${DEFAULT_DELAY:-0.08}"
DEFAULT_CYCLES="${DEFAULT_CYCLES:-18}"

_loader_frames() {
    case "${1:-dots3}" in
        dots3)   printf '. .. ... .... ... .. .\n' ;;
        bar)     printf '[    ] [=   ] [==  ] [=== ] [====] [ ===] [  ==] [   =]\n' ;;
        orbit)   printf '◐ ◓ ◑ ◒\n' ;;
        pulse)   printf '· • ● •\n' ;;
        blade)   printf '| / - \\\n' ;;
        crawl)   printf '▁ ▂ ▃ ▄ ▅ ▆ ▇ █ ▇ ▆ ▅ ▄ ▃ ▂\n' ;;
        arc)     printf '◜ ◠ ◝ ◞ ◡ ◟\n' ;;
        leaf)    printf '🌱 🌿 🍃 🍂 🍁 🍂 🍃 🌿\n' ;;
        braille) printf '⣾ ⣽ ⣻ ⢿ ⡿ ⣟ ⣯ ⣷\n' ;;
        *)       printf '. .. ...\n' ;;
    esac
}

leaf_loader_list() {
    cat <<LIST
dots3
bar
orbit
pulse
blade
crawl
arc
leaf
braille
LIST
}

# leaf_loader_run NAME LABEL [CYCLES [DELAY]]
# Colored animated spinner. Resolves with a ✓ done line.
leaf_loader_run() {
    local name="${1:-$DEFAULT_LOADER}"
    local label="${2:-loading}"
    local cycles="${3:-$DEFAULT_CYCLES}"
    local delay="${4:-$DEFAULT_DELAY}"

    local frames
    IFS=' ' read -r -a frames <<< "$(_loader_frames "$name")"

    if [[ ${#frames[@]} -eq 0 ]]; then
        brand_warn "loader '$name' has no frames"
        return 1
    fi

    if ! leaf_motion_enabled; then
        printf '  %s[READY]%s %s\n' "$C_GREEN_B" "$C_RESET" "$label"
        return 0
    fi

    local n=${#frames[@]}
    for ((i=0; i<cycles; i++)); do
        printf '\r  %s%s%s  %s%s%s %s' \
            "$C_CYAN" "${frames[$((i % n))]}" "$C_RESET" \
            "$C_DIM" "$label" "$C_RESET" ""
        sleep "$delay"
    done
    printf '\r  %s✓%s  %s%-40s%s\n' \
        "$C_GREEN_B" "$C_RESET" "$C_DIM" "$label done" "$C_RESET"
}

# leaf_loader_run_timed CMD LABEL [NAME [DELAY]]
# Run CMD in background while showing animation. Resolve ✓/✗ on exit.
leaf_loader_run_timed() {
    local cmd=("$1"); shift
    # If more than one word was passed as cmd, handle it
    local label="${1:-running}"; shift || true
    local name="${1:-orbit}";    shift || true
    local delay="${1:-0.10}";    shift || true

    local frames
    IFS=' ' read -r -a frames <<< "$(_loader_frames "$name")"
    local n=${#frames[@]}

    # Run command, capturing exit code without set -e killing us.
    local tmpout; tmpout="$(mktemp)"
    ("${cmd[@]}" >"$tmpout" 2>&1) &
    local pid=$!

    local i=0
    if leaf_motion_enabled; then
        while kill -0 "$pid" 2>/dev/null; do
            printf '\r  %s%s%s  %s%s%s' \
                "$C_CYAN" "${frames[$((i % n))]}" "$C_RESET" \
                "$C_DIM" "$label" "$C_RESET"
            i=$((i+1))
            sleep "$delay"
        done
    fi

    wait "$pid"
    local rc=$?

    if [[ $rc -eq 0 ]]; then
        printf '\r  %s✓%s  %-44s\n' "$C_GREEN_B" "$C_RESET" "$label"
    else
        printf '\r  %s✗%s  %-44s\n' "$C_RED_B"   "$C_RESET" "$label failed (exit $rc)"
        cat "$tmpout" >&2
    fi
    rm -f "$tmpout"
    return $rc
}

# leaf_progress_bar CURRENT TOTAL LABEL
# Colored filled/empty block progress bar.
leaf_progress_bar() {
    local cur="$1" total="$2" label="${3:-}"
    local width=30
    if ! leaf_motion_enabled; then
        printf '  [%3d%%] %s\n' $(( cur * 100 / total )) "$label"
        return 0
    fi
    local filled=$(( cur * width / total ))
    local empty=$(( width - filled ))
    local bar_f bar_e
    printf -v bar_f '%*s' "$filled" ''; bar_f="${bar_f// /█}"
    printf -v bar_e '%*s' "$empty"  ''; bar_e="${bar_e// /░}"
    printf '\r  %s%s%s%s%s%s  %3d%%  %s' \
        "$C_GREEN"   "$bar_f" \
        "$C_DIM"     "$bar_e" \
        "$C_RESET"   "" \
        $(( cur * 100 / total )) \
        "$label"
}
