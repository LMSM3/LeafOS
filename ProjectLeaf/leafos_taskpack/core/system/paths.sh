#!/usr/bin/env bash
# Shared path resolver for LeafOS scripts.

leaf_root() {
    local src="${BASH_SOURCE[0]}"
    while [[ -h "$src" ]]; do
        local dir
        dir="$(cd -P "$(dirname "$src")" && pwd)"
        src="$(readlink "$src")"
        [[ "$src" != /* ]] && src="$dir/$src"
    done
    cd -P "$(dirname "$src")/../.." && pwd
}

LEAF_ROOT="${LEAF_ROOT:-$(leaf_root)}"
LEAF_CONFIG_DIR="$LEAF_ROOT/config"
LEAF_LOG_DIR="$LEAF_ROOT/logs"
LEAF_SHARE_DIR="$LEAF_ROOT/share"
LEAF_BIN_DIR="$LEAF_ROOT/bin"
