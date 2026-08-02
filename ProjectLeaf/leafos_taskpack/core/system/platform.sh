#!/usr/bin/env bash
# core/system/platform.sh -- cross-platform detection for LeafOS
# Supports: macOS, Linux, WSL (Windows Subsystem for Linux), Windows (MSYS2/Git Bash)

leaf_detect_platform() {
    local uname_s uname_m
    uname_s="$(uname -s 2>/dev/null || echo unknown)"
    uname_m="$(uname -m 2>/dev/null || echo unknown)"

    case "$uname_m" in
        x86_64|amd64)  LEAF_ARCH=x86_64 ;;
        arm64|aarch64) LEAF_ARCH=arm64  ;;
        *)             LEAF_ARCH="$uname_m" ;;
    esac

    case "$uname_s" in
        Darwin)
            LEAF_OS=mac
            LEAF_OS_NAME="macOS $(sw_vers -productVersion 2>/dev/null || echo unknown)"
            LEAF_INSTALL_PREFIX="${HOME}/.local"
            LEAF_BIN_EXT=""
            ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null || \
               grep -qi wsl      /proc/version 2>/dev/null; then
                LEAF_OS=wsl
                _d="$(grep -oP '(?<=^NAME=")[^"]+' /etc/os-release 2>/dev/null || echo Linux)"
                LEAF_OS_NAME="WSL ($_d)"
            else
                LEAF_OS=linux
                LEAF_OS_NAME="$(grep -oP '(?<=^NAME=")[^"]+' /etc/os-release 2>/dev/null || echo Linux)"
            fi
            LEAF_INSTALL_PREFIX="${HOME}/.local"
            LEAF_BIN_EXT=""
            ;;
        MINGW*|MSYS*|CYGWIN*)
            LEAF_OS=windows
            LEAF_OS_NAME="Windows ($uname_s)"
            LEAF_INSTALL_PREFIX="${USERPROFILE:-$HOME}/AppData/Local/leafos"
            LEAF_BIN_EXT=".exe"
            ;;
        *)
            LEAF_OS=unknown
            LEAF_OS_NAME="$uname_s"
            LEAF_INSTALL_PREFIX="${HOME}/.local"
            LEAF_BIN_EXT=""
            ;;
    esac

    export LEAF_OS LEAF_ARCH LEAF_OS_NAME LEAF_INSTALL_PREFIX LEAF_BIN_EXT
}

leaf_is_mac()     { [[ "${LEAF_OS:-}" == mac     ]]; }
leaf_is_linux()   { [[ "${LEAF_OS:-}" == linux   ]]; }
leaf_is_wsl()     { [[ "${LEAF_OS:-}" == wsl     ]]; }
leaf_is_windows() { [[ "${LEAF_OS:-}" == windows ]]; }
leaf_is_posix()   { [[ "${LEAF_OS:-}" != windows ]]; }

leaf_platform_summary() {
    printf 'os=%s arch=%s name="%s"\n' "$LEAF_OS" "$LEAF_ARCH" "$LEAF_OS_NAME"
}

leaf_detect_platform
