#!/usr/bin/env bash
# Run a small Bash-side LeafOS demo.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$HERE/leaf.sh" status
bash "$HERE/leaf.sh" runtime select
bash "$HERE/leaf.sh" runtime workers 0.42 tests_failed
