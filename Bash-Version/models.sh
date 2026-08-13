#!/usr/bin/env bash
# Compatibility wrapper for the real-model-first workflow.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/real-models.sh" "$@"
