#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/core/brand/brand.sh"
source "$ROOT_DIR/core/log/log.sh"

brand_say "module started"
leaf_log INFO "module started"
