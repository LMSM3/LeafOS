#!/usr/bin/env bash
# Run a small Bash-side LeafOS demo.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$HERE/leaf.sh" status
bash "$HERE/leaf.sh" runtime select
bash "$HERE/leaf.sh" runtime workers 0.42 tests_failed
