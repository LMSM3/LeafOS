#!/usr/bin/env bash
# core/system/versions.sh -- version detection and compatibility checks for LeafOS

[[ -n "${LEAF_ROOT:-}" ]] || LEAF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

_leaf_ver_conf() {
    grep -E "^$1=" "$LEAF_ROOT/config/versions.conf" 2>/dev/null | cut -d= -f2 | tr -d '[:space:]'
}

# Returns 0 if version $1 >= version $2 (X.Y format)
leaf_version_gte() {
    local have="$1" need="$2"
    local have_maj have_min need_maj need_min
    have_maj="${have%%.*}" ; have_min="${have#*.}" ; have_min="${have_min%%.*}"
    need_maj="${need%%.*}" ; need_min="${need#*.}" ; need_min="${need_min%%.*}"
    [[ "$have_maj" -gt "$need_maj" ]] && return 0
    [[ "$have_maj" -eq "$need_maj" && "${have_min:-0}" -ge "${need_min:-0}" ]] && return 0
    return 1
}

leaf_detect_bash() {
    LEAF_VER_BASH="${BASH_VERSION%%(*}" ; LEAF_VER_BASH="${LEAF_VER_BASH%%-*}"
    export LEAF_VER_BASH
}

leaf_detect_python() {
    if command -v python3 &>/dev/null; then
        LEAF_VER_PYTHON="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
        LEAF_PYTHON_CMD=python3
    elif command -v python &>/dev/null; then
        local _v
        _v="$(python -c 'import sys; print(sys.version_info[0])' 2>/dev/null || echo 0)"
        if [[ "$_v" == "3" ]]; then
            LEAF_VER_PYTHON="$(python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
            LEAF_PYTHON_CMD=python
        else
            LEAF_VER_PYTHON=0.0 ; LEAF_PYTHON_CMD=""
        fi
    else
        LEAF_VER_PYTHON=0.0 ; LEAF_PYTHON_CMD=""
    fi
    export LEAF_VER_PYTHON LEAF_PYTHON_CMD
}

leaf_detect_cc() {
    if   command -v cc    &>/dev/null; then LEAF_CC=cc
    elif command -v gcc   &>/dev/null; then LEAF_CC=gcc
    elif command -v clang &>/dev/null; then LEAF_CC=clang
    else LEAF_CC=""
    fi
    if [[ -n "$LEAF_CC" ]]; then
        LEAF_VER_CC="$($LEAF_CC --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo 0.0)"
    else
        LEAF_VER_CC=0.0
    fi
    export LEAF_CC LEAF_VER_CC
}

leaf_detect_pwsh() {
    local candidate version major fallback_cmd="" fallback_ver="" item
    local -a candidates=()
    for item in pwsh pwsh.exe powershell powershell.exe; do
        candidate="$(command -v "$item" 2>/dev/null || true)"
        [[ -n "$candidate" ]] && candidates+=("$candidate")
    done
    candidates+=(
        "/c/Users/${USERNAME:-${USER:-}}/AppData/Local/Microsoft/WindowsApps/pwsh.exe"
        "/c/Program Files/PowerShell/7/pwsh.exe"
        "/mnt/c/Users/${USERNAME:-${USER:-}}/AppData/Local/Microsoft/WindowsApps/pwsh.exe"
        "/mnt/c/Program Files/PowerShell/7/pwsh.exe"
        "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe"
    )
    LEAF_PWSH_CMD=""; LEAF_VER_PWSH=0.0; LEAF_PWSH_KIND=missing
    for candidate in "${candidates[@]}"; do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        version="$("$candidate" -NoLogo -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()' 2>/dev/null | tr -d '\r' || true)"
        [[ "$version" =~ ^[0-9]+([.][0-9]+)+$ ]] || continue
        major="${version%%.*}"
        if [[ "$major" -ge 7 ]]; then
            LEAF_PWSH_CMD="$candidate"; LEAF_VER_PWSH="$version"
            break
        fi
        if [[ -z "$fallback_cmd" && "$major" -ge 5 ]]; then
            fallback_cmd="$candidate"; fallback_ver="$version"
        fi
    done
    if [[ -z "$LEAF_PWSH_CMD" && -n "$fallback_cmd" ]]; then
        LEAF_PWSH_CMD="$fallback_cmd"; LEAF_VER_PWSH="$fallback_ver"
    fi
    if [[ -n "$LEAF_PWSH_CMD" ]]; then
        case "$LEAF_PWSH_CMD" in
            *.exe|/mnt/[a-zA-Z]/*|/c/*) LEAF_PWSH_KIND=windows-interop ;;
            *) LEAF_PWSH_KIND=native ;;
        esac
    fi
    export LEAF_PWSH_CMD LEAF_VER_PWSH LEAF_PWSH_KIND
}

# Evaluate the detected host against a caller-specific language floor. Detection
# intentionally knows about every supported fallback; the caller owns whether a
# particular capability needs PowerShell 5, 7, or a later version.
leaf_pwsh_meets() {
    local required="${1:-7.0}"
    [[ -n "${LEAF_PWSH_CMD:-}" ]] || return 1
    leaf_version_gte "${LEAF_VER_PWSH:-0.0}" "$required"
}

leaf_detect_all_versions() {
    leaf_detect_bash ; leaf_detect_python ; leaf_detect_cc ; leaf_detect_pwsh
}

leaf_check_versions() {
    local ok=1
    local min_bash min_python min_cc min_pwsh
    min_bash="$(_leaf_ver_conf LEAF_MIN_BASH    || echo 4.0)"
    min_python="$(_leaf_ver_conf LEAF_MIN_PYTHON || echo 3.8)"
    min_cc="$(_leaf_ver_conf LEAF_MIN_GCC        || echo 9.0)"
    min_pwsh="$(_leaf_ver_conf LEAF_MIN_PWSH     || echo 7.0)"

    printf '%-16s %-12s %-12s %s\n' component found required status
    printf '%s\n' '----------------------------------------------------'

    _leaf_ver_row() {
        local name="$1" found="$2" need="$3"
        local st=ok
        if [[ "$found" == "0.0" || "$found" == "none" ]]; then
            st=missing ; ok=0
        else
            leaf_version_gte "$found" "$need" || { st=WARN ; ok=0; }
        fi
        printf '%-16s %-12s %-12s %s\n' "$name" "$found" "$need" "$st"
    }

    _leaf_ver_row bash       "${LEAF_VER_BASH:-0.0}"   "$min_bash"
    _leaf_ver_row python     "${LEAF_VER_PYTHON:-0.0}" "$min_python"
    _leaf_ver_row "${LEAF_CC:-cc}" "${LEAF_VER_CC:-0.0}" "$min_cc"
    _leaf_ver_row powershell "${LEAF_VER_PWSH:-0.0}"   "$min_pwsh"

    [[ "$ok" -eq 1 ]]
}

leaf_versions_report() {
    printf 'LeafOS version matrix\n---------------------\n'
    leaf_detect_all_versions
    leaf_check_versions
}
