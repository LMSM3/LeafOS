#!/usr/bin/env bash
# bin/install_demo.sh -- LeafOS demo installer (Linux / WSL)
# Usage: bash bin/install_demo.sh [PREFIX]
set -euo pipefail

PREFIX="${1:-$HOME/.local}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARE_DIR="$PREFIX/share/leafos"
BIN_DIR="$PREFIX/bin"

# --- source brand helpers if already installed, else fall back to plain echo
if [[ -f "$ROOT_DIR/core/brand/brand.sh" ]]; then
    # shellcheck disable=SC1090
    source "$ROOT_DIR/core/brand/brand.sh"
else
    brand_banner() { echo "LeafOS"; }
    brand_header() { echo "--- $* ---"; }
    brand_say()    { echo "› $*"; }
    brand_ok()     { echo "✓ $*"; }
    brand_kv()     { printf '  %-18s %s\n' "$1" "$2"; }
fi

brand_banner
brand_header "LeafOS Demo Install"
brand_kv "prefix" "$PREFIX"
brand_kv "share"  "$SHARE_DIR"
brand_kv "bin"    "$BIN_DIR"
printf '\n'

mkdir -p "$BIN_DIR" "$SHARE_DIR"
cp -R "$ROOT_DIR"/* "$SHARE_DIR/"
ln -sf "$SHARE_DIR/bin/leafctl" "$BIN_DIR/leafctl"
ln -sf "$SHARE_DIR/bin/leafctl" "$BIN_DIR/leaf"
ln -sf "$SHARE_DIR/bin/flowerctl" "$BIN_DIR/leafos"
ln -sf "$SHARE_DIR/bin/flowerctl" "$BIN_DIR/flower"

brand_ok "Files installed to $SHARE_DIR"
brand_ok "leafos, leaf, flower, and leafctl linked at $BIN_DIR"

if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    printf '\n'
    brand_say "Add to your shell rc:  export PATH=\"$BIN_DIR:\$PATH\""
fi

printf '\n'
brand_kv "quick syntax" "leafos q"
brand_kv "home" "leafos"
brand_kv "full help" "leafos help"
printf '\n'

# --- post-install: model grab + CUDA/deps loop
POST="$SHARE_DIR/bin/post_install.sh"
if [[ -f "$POST" ]]; then
    bash "$POST"
else
    brand_say "Post-install script not found at $POST -- skipping."
fi
