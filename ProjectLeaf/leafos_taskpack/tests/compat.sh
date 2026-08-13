#!/usr/bin/env bash
# tests/compat.sh -- cross-platform compatibility matrix test
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source "$ROOT_DIR/core/system/platform.sh"
source "$ROOT_DIR/core/system/versions.sh"
leaf_detect_all_versions

echo "LeafOS Compatibility Matrix"
echo "==========================="
echo ""
echo "Platform"
leaf_platform_summary
echo ""
echo "Version Check"
leaf_check_versions
echo ""
echo "Available Layers"
echo "----------------"

if command -v bash &>/dev/null; then
    if "$ROOT_DIR/bin/leafctl" doctor &>/dev/null; then
        echo "  bash      : ok"
    else
        echo "  bash      : fail"
    fi
else
    echo "  bash      : missing"
fi

if command -v python3 &>/dev/null && [[ -f "$ROOT_DIR/bin/leafpy" ]]; then
    if python3 "$ROOT_DIR/bin/leafpy" doctor &>/dev/null; then
        echo "  python    : ok"
    else
        echo "  python    : fail"
    fi
else
    echo "  python    : skip"
fi

_pwsh=""
command -v pwsh       &>/dev/null && _pwsh=pwsh
command -v powershell &>/dev/null && [[ -z "$_pwsh" ]] && _pwsh=powershell

if [[ -n "$_pwsh" && -f "$ROOT_DIR/bin/leafctl.ps1" ]]; then
    if "$_pwsh" -NoProfile -File "$ROOT_DIR/bin/leafctl.ps1" doctor &>/dev/null; then
        echo "  powershell: ok"
    else
        echo "  powershell: fail"
    fi
else
    echo "  powershell: skip"
fi

[[ -x "$ROOT_DIR/build/leaf_loader_demo"    ]] && echo "  c (v1)    : built" || echo "  c (v1)    : not built"
[[ -x "$ROOT_DIR/build/leaf_loader_demo_v2" ]] && echo "  c (v2)    : built" || echo "  c (v2)    : not built"

echo ""
echo "compat.sh: done"
