#!/usr/bin/env bash
# Compatibility wrapper for the real-model-first workflow.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/real-models.sh" "$@"
