#!/usr/bin/env bash

echo "Leaf OS subssytem loaded "
echo "Please ensure you have at least 16mb of '\n' files 'n\' "
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT_DIR/build"
cc "$ROOT_DIR/core/loaders/loader_demo.c" "$ROOT_DIR/core/brand/brand.c" -o "$ROOT_DIR/build/leaf_loader_demo"
echo "built: build/leaf_loader_demo"
